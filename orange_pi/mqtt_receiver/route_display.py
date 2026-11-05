import math
import os
import threading
import time
from pathlib import Path
from typing import Optional
from urllib.error import URLError
from urllib.request import Request, urlopen

from PIL import Image, ImageDraw, ImageFont

from ili9341_opi import ILI9341

try:
    from xpt2046_opi import Touch
except ImportError:
    Touch = None


TILE_SIZE = 256
TILE_URL = os.getenv(
    "OSM_TILE_URL", "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
)
CACHE_DIR = Path(os.getenv("OSM_CACHE_DIR", "osm_tiles"))
USER_AGENT = "proyecto-sistemas-embebidos/1.0"
VIEW_RADII_M = (50.0, 250.0, 1000.0, 5000.0, 10000.0)
INITIAL_RADIUS_M = float(os.getenv("OSM_VIEW_RADIUS_M", "1000"))
TOUCH_DEBUG = os.getenv("TOUCH_DEBUG", "0") == "1"
TOUCH_X_MIN = int(os.getenv("TOUCH_X_MIN", "300"))
TOUCH_X_MAX = int(os.getenv("TOUCH_X_MAX", "3800"))
TOUCH_Y_MIN = int(os.getenv("TOUCH_Y_MIN", "300"))
TOUCH_Y_MAX = int(os.getenv("TOUCH_Y_MAX", "3800"))
TOUCH_SWAP_AXES = os.getenv("TOUCH_SWAP_AXES", "0") == "1"
TOUCH_INVERT_X = os.getenv("TOUCH_INVERT_X", "0") == "1"
TOUCH_INVERT_Y = os.getenv("TOUCH_INVERT_Y", "0") == "1"


def _world_pixel(latitude: float, longitude: float, zoom: int) -> tuple[float, float]:
    latitude = max(-85.05112878, min(85.05112878, latitude))
    scale = TILE_SIZE * (2**zoom)
    x = (longitude + 180.0) / 360.0 * scale
    sine = math.sin(math.radians(latitude))
    y = (0.5 - math.log((1 + sine) / (1 - sine)) / (4 * math.pi)) * scale
    return x, y


class RouteDisplay:
    def __init__(self) -> None:
        self.display = ILI9341(
            bus=1,
            dispositivo=0,
            dc=261,
            cs=229,
            rst=227,
            rotacion=0,
            baudrate=40000000,
        )
        self.width = self.display.width
        self.height = self.display.height
        self.points: list[tuple[float, float]] = []
        self.lock = threading.Lock()
        self.font = ImageFont.load_default()
        try:
            self.control_font = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 22
            )
        except OSError:
            self.control_font = self.font
        self.radius_index = min(
            range(len(VIEW_RADII_M)),
            key=lambda index: abs(VIEW_RADII_M[index] - INITIAL_RADIUS_M),
        )
        self.touch = self._create_touch()
        self.last_touch = 0.0
        self.clear()
        if self.touch is not None:
            threading.Thread(target=self._touch_loop, daemon=True).start()

    def _create_touch(self):
        if Touch is None:
            return None
        try:
            return Touch(bus=1, dispositivo=1, irq=226, baudrate=4000000)
        except (OSError, RuntimeError) as error:
            print(f"Panel táctil no disponible: {error}")
            return None

    def _touch_loop(self) -> None:
        while True:
            try:
                if self.touch.is_pressed():
                    raw_x, raw_y = self.touch.get_coordinates()
                    x, y = self._touch_to_screen(raw_x, raw_y)
                    now = time.monotonic()
                    if TOUCH_DEBUG:
                        print(
                            f"Touch crudo: x={raw_x}, y={raw_y}; "
                            f"pantalla: x={x}, y={y}",
                            flush=True,
                        )
                    if now - self.last_touch >= 0.4:
                        if 0 <= x <= 70 and 0 <= y <= 70:
                            print("Touch: zoom out", flush=True)
                            self._change_radius(-1)
                        elif self.width - 70 <= x <= self.width and 0 <= y <= 70:
                            print("Touch: zoom in", flush=True)
                            self._change_radius(1)
                        self.last_touch = now
            except (OSError, RuntimeError, TypeError, ValueError):
                pass
            time.sleep(0.05)

    def _touch_to_screen(self, raw_x: int, raw_y: int) -> tuple[int, int]:
        if TOUCH_SWAP_AXES:
            raw_x, raw_y = raw_y, raw_x
        x = round((raw_x - TOUCH_X_MIN) * self.width /
                  (TOUCH_X_MAX - TOUCH_X_MIN))
        y = round((raw_y - TOUCH_Y_MIN) * self.height /
                  (TOUCH_Y_MAX - TOUCH_Y_MIN))
        if TOUCH_INVERT_X:
            x = self.width - x
        if TOUCH_INVERT_Y:
            y = self.height - y
        return max(0, min(self.width, x)), max(0, min(self.height, y))

    def _change_radius(self, direction: int) -> None:
        with self.lock:
            self.radius_index = max(
                0, min(len(VIEW_RADII_M) - 1, self.radius_index + direction)
            )
            self._render()

    def clear(self) -> None:
        with self.lock:
            self.points.clear()
            self._render()

    def add_point(self, latitude: float, longitude: float) -> None:
        with self.lock:
            self.points.append((latitude, longitude))
            self._render()

    def _select_zoom(self, latitude: float) -> int:
        radius_m = VIEW_RADII_M[self.radius_index]
        lat_delta = radius_m / 111_320.0
        lon_delta = radius_m / (111_320.0 * max(0.1, math.cos(math.radians(latitude))))
        for zoom in range(19, 9, -1):
            center_x, center_y = _world_pixel(latitude, 0, zoom)
            east_x, _ = _world_pixel(latitude, lon_delta, zoom)
            _, north_y = _world_pixel(latitude + lat_delta, 0, zoom)
            if (east_x - center_x) * 2 <= self.width - 16 and \
                    (center_y - north_y) * 2 <= self.height - 28:
                return zoom
        return 10

    def _tile_path(self, zoom: int, tile_x: int, tile_y: int) -> Path:
        return CACHE_DIR / str(zoom) / str(tile_x) / f"{tile_y}.png"

    def _get_tile(self, zoom: int, tile_x: int, tile_y: int) -> Optional[Image.Image]:
        tiles_per_axis = 2**zoom
        tile_x %= tiles_per_axis
        if tile_y < 0 or tile_y >= tiles_per_axis:
            return None
        path = self._tile_path(zoom, tile_x, tile_y)
        try:
            if not path.exists():
                request = Request(
                    TILE_URL.format(z=zoom, x=tile_x, y=tile_y),
                    headers={"User-Agent": USER_AGENT},
                )
                with urlopen(request, timeout=8) as response:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(response.read())
            return Image.open(path).convert("RGB")
        except (OSError, URLError, TimeoutError) as error:
            print(f"No se pudo cargar mosaico OSM {zoom}/{tile_x}/{tile_y}: {error}")
            return None

    def _map_image(self, zoom: int, center_x: float, center_y: float) -> Image.Image:
        first_tile_x = math.floor((center_x - self.width / 2) / TILE_SIZE)
        first_tile_y = math.floor((center_y - self.height / 2) / TILE_SIZE)
        tile_columns = math.ceil(self.width / TILE_SIZE) + 2
        tile_rows = math.ceil(self.height / TILE_SIZE) + 2
        image = Image.new(
            "RGB",
            (tile_columns * TILE_SIZE, tile_rows * TILE_SIZE),
            (235, 235, 235),
        )
        for tile_y in range(first_tile_y, first_tile_y + 3):
            for tile_x in range(first_tile_x, first_tile_x + 3):
                tile = self._get_tile(zoom, tile_x, tile_y)
                if tile is not None:
                    image.paste(
                        tile,
                        ((tile_x - first_tile_x) * TILE_SIZE,
                         (tile_y - first_tile_y) * TILE_SIZE),
                    )
        origin_x = first_tile_x * TILE_SIZE
        origin_y = first_tile_y * TILE_SIZE
        crop_left = round(center_x - self.width / 2 - origin_x)
        crop_top = round(center_y - self.height / 2 - origin_y)
        return image.crop((crop_left, crop_top, crop_left + self.width,
                           crop_top + self.height))

    def _draw_controls(self, image: Image.Image) -> None:
        draw = ImageDraw.Draw(image)
        button_size = 48
        top = 6
        draw.rounded_rectangle(
            (6, top, 6 + button_size, top + button_size),
            radius=6, fill=(0, 80, 180), outline=(255, 255, 255), width=2,
        )
        draw.rounded_rectangle(
            (self.width - 6 - button_size, top, self.width - 6, top + button_size),
            radius=6, fill=(0, 80, 180), outline=(255, 255, 255), width=2,
        )
        draw.text((21, top + 8), "-", fill=(255, 255, 255), font=self.control_font)
        draw.text(
            (self.width - 39, top + 8), "+",
            fill=(255, 255, 255), font=self.control_font,
        )

    def _render(self) -> None:
        if not self.points:
            image = Image.new("RGB", (self.width, self.height), (0, 0, 0))
            ImageDraw.Draw(image).text(
                (12, 12), "Esperando coordenadas...", fill=(255, 255, 255),
                font=self.font,
            )
            self._draw_controls(image)
            self.display.image(image)
            return

        center_lat = sum(point[0] for point in self.points) / len(self.points)
        center_lon = sum(point[1] for point in self.points) / len(self.points)
        zoom = self._select_zoom(center_lat)
        world_points = [_world_pixel(lat, lon, zoom) for lat, lon in self.points]
        center_x, center_y = _world_pixel(center_lat, center_lon, zoom)
        image = self._map_image(zoom, center_x, center_y)
        draw = ImageDraw.Draw(image)
        pixels = [
            (round(x - center_x + self.width / 2),
             round(y - center_y + self.height / 2))
            for x, y in world_points
        ]
        if len(pixels) > 1:
            draw.line(pixels, fill=(0, 80, 255), width=3)
        start_x, start_y = pixels[0]
        end_x, end_y = pixels[-1]
        draw.ellipse((start_x - 5, start_y - 5, start_x + 5, start_y + 5),
                     fill=(0, 180, 0))
        draw.ellipse((end_x - 5, end_y - 5, end_x + 5, end_y + 5),
                     fill=(220, 0, 0))
        draw.rectangle((0, self.height - 25, self.width, self.height), fill=(0, 0, 0))
        radius = VIEW_RADII_M[self.radius_index]
        draw.text((3, self.height - 23), f"{len(pixels)} puntos | radio {radius:.0f} m",
                  fill=(255, 255, 255), font=self.font)
        draw.text((3, self.height - 12), "© OpenStreetMap contributors",
                  fill=(255, 255, 255), font=self.font)
        self._draw_controls(image)
        self.display.image(image)


def create_route_display() -> Optional[RouteDisplay]:
    try:
        return RouteDisplay()
    except (ImportError, OSError, RuntimeError) as error:
        print(f"ILI9341 no disponible; se continuará sin pantalla: {error}")
        return None
