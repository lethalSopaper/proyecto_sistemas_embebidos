import math
import os
import threading
import time
from pathlib import Path
from typing import Optional

from mysql.connector import Error as MySQLError
from PIL import Image, ImageDraw, ImageFont

from ili9341_opi import ILI9341
from route_statistics import RouteStatistics

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
    def __init__(self, route_database) -> None:
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
        self.route_database = route_database
        self.screen = "menu"
        self.sort_by = "date"
        self.routes: list[dict[str, object]] = []
        self.routes_error: str | None = None
        self.page = 0
        self.statistics_page = 0
        self.statistics = RouteStatistics.empty()
        self.statistics_error: str | None = None
        self.selected_route_id: int | None = None
        self.lock = threading.Lock()
        self.display_lock = threading.Lock()
        self.font = ImageFont.load_default()
        try:
            bold_font = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
            self.control_font = ImageFont.truetype(bold_font, 22)
            self.stats_value_font = ImageFont.truetype(bold_font, 16)
        except OSError:
            self.control_font = self.font
            self.stats_value_font = self.font
        self.radius_index = min(
            range(len(VIEW_RADII_M)),
            key=lambda index: abs(VIEW_RADII_M[index] - INITIAL_RADIUS_M),
        )
        self.touch = self._create_touch()
        self.last_touch = 0.0
        self._refresh_routes()
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
                        if TOUCH_DEBUG:
                            print(
                                f"Accion touch: pantalla={self.screen}, "
                                f"x={x}, y={y}",
                                flush=True,
                            )
                        if self.screen == "menu":
                            self._handle_menu_touch(x, y)
                        elif self.screen == "statistics":
                            self._handle_statistics_touch(x, y)
                        elif 88 <= x <= 152 and 0 <= y <= 55:
                            self._show_menu()
                        elif 0 <= x <= 70 and 0 <= y <= 70:
                            print("Touch: zoom out", flush=True)
                            self._change_radius(1)
                        elif self.width - 70 <= x <= self.width and 0 <= y <= 70:
                            print("Touch: zoom in", flush=True)
                            self._change_radius(-1)
                        self.last_touch = now
            except (OSError, RuntimeError, TypeError, ValueError) as error:
                if TOUCH_DEBUG:
                    print(
                        f"Error procesando touch en pantalla "
                        f"{self.screen}: {error}",
                        flush=True,
                    )
            time.sleep(0.05)

    def _handle_menu_touch(self, x: int, y: int) -> None:
        if y < 58 and x < self.width // 2:
            with self.lock:
                self.sort_by = "name" if self.sort_by == "date" else "date"
                self.page = 0
            self._refresh_routes()
        elif y < 58:
            self._show_statistics()
        elif y >= self.height - 42 and x < self.width // 2:
            self.page = max(0, self.page - 1)
            self._render_menu()
        elif y >= self.height - 42:
            last_page = max(0, (len(self.routes) - 1) // 6)
            self.page = min(last_page, self.page + 1)
            self._render_menu()
        elif 58 <= y < self.height - 42:
            index = self.page * 6 + (y - 58) // 23
            if index < len(self.routes):
                route = self.routes[index]
                route_id = int(route["id"])
                try:
                    points = self.route_database.get_route_points(route_id)
                except MySQLError as error:
                    with self.lock:
                        self.routes_error = str(error)
                    print(f"No se pudo cargar la ruta: {error}", flush=True)
                    with self.lock:
                        self.screen = "menu"
                    self._render_menu()
                    return
                with self.lock:
                    self.selected_route_id = route_id
                    self.points = points
                    self.routes_error = None
                    self.screen = "map"
                self._render()

    def _show_statistics(self) -> None:
        with self.lock:
            self.screen = "statistics"
            self.statistics_page = 0
            self.statistics_error = None
        try:
            self.statistics = self.route_database.get_statistics()
        except MySQLError as error:
            self.statistics_error = str(error)
            print(f"No se pudieron consultar las estadísticas: {error}",
                  flush=True)
        self._render_statistics()

    def _handle_statistics_touch(self, x: int, y: int) -> None:
        if y <= 32 and x < 72:
            self._show_menu()
        elif y >= self.height - 32:
            with self.lock:
                self.statistics_page = 1 - self.statistics_page
            self._render_statistics()

    def _refresh_routes(self) -> None:
        try:
            routes = self.route_database.list_routes(self.sort_by)
            route_error = None
        except MySQLError as error:
            routes = []
            route_error = str(error)
            print(f"No se pudieron cargar las rutas: {error}", flush=True)
        with self.lock:
            self.routes = routes
            self.routes_error = route_error
        self._render_menu()

    def _show_menu(self) -> None:
        with self.lock:
            self.screen = "menu"
            self.page = 0
        self._refresh_routes()

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
            self.screen = "map"
        self._render()

    def add_point(self, latitude: float, longitude: float) -> None:
        with self.lock:
            self.points.append((latitude, longitude))
            render_map = self.screen == "map"
        if render_map:
            self._render()

    def _select_zoom(self, latitude: float, radius_index: int) -> int:
        radius_m = VIEW_RADII_M[radius_index]
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
        draw.rounded_rectangle(
            (88, top, 152, top + button_size),
            radius=6, fill=(0, 80, 180), outline=(255, 255, 255), width=2,
        )
        draw.text((108, top + 12), "R", fill=(255, 255, 255), font=self.font)

    def _render_menu(self) -> None:
        image = Image.new("RGB", (self.width, self.height), (20, 25, 35))
        draw = ImageDraw.Draw(image)
        draw.text((8, 4), "Rutas guardadas", fill=(255, 255, 255), font=self.control_font)
        draw.rectangle((0, 30, self.width // 2 - 2, 56),
                       fill=(0, 80, 150), outline=(255, 255, 255))
        draw.rectangle((self.width // 2 + 2, 30, self.width - 1, 56),
                       fill=(0, 110, 90), outline=(255, 255, 255))
        order_label = "Orden: fecha" if self.sort_by == "date" else "Orden: nombre"
        draw.text((8, 38), order_label, fill=(255, 255, 255), font=self.font)
        draw.text((self.width // 2 + 12, 38), "Estadísticas",
                  fill=(255, 255, 255), font=self.font)
        start = self.page * 6
        visible = self.routes[start:start + 6]
        if self.routes_error is not None:
            draw.text((8, 92), "No se pudieron cargar las rutas",
                      fill=(255, 180, 180), font=self.font)
            draw.text((8, 110), "Revisa los logs y MariaDB",
                      fill=(255, 255, 255), font=self.font)
        else:
            for row, route in enumerate(visible):
                top = 58 + row * 23
                draw.rectangle((4, top, self.width - 4, top + 21),
                               fill=(40, 50, 65), outline=(100, 110, 125))
                name = str(route.get("name") or f"Ruta {route['id']}")
                draw.text((9, top + 1), name[:34],
                          fill=(255, 255, 255), font=self.font)
                date = route["started_at"].strftime("%Y-%m-%d %H:%M")
                points = int(route.get("point_count") or 0)
                distance = float(route.get("distance_m") or 0)
                draw.text((9, top + 12),
                          f"{date} | {distance / 1000:.2f} km | {points} pts",
                          fill=(190, 210, 225), font=self.font)
        draw.rectangle((0, self.height - 42, self.width, self.height),
                       fill=(0, 0, 0))
        total_pages = max(1, (len(self.routes) + 5) // 6)
        draw.text((8, self.height - 30),
                  f"{self.page + 1}/{total_pages}  {len(self.routes)} rutas",
                  fill=(255, 255, 255), font=self.font)
        draw.text((self.width // 2 + 12, self.height - 30),
                  "< anterior        siguiente >", fill=(255, 255, 255),
                  font=self.font)
        self._display_image(image, "menu")

    def _display_image(self, image: Image.Image, expected_screen: str) -> None:
        with self.display_lock:
            with self.lock:
                if self.screen != expected_screen:
                    return
                self.display.image(image)

    def _render_statistics(self) -> None:
        image = Image.new("RGB", (self.width, self.height), (20, 25, 35))
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, self.width, 28), fill=(0, 0, 0))
        draw.text((6, 8), "< Rutas", fill=(255, 255, 255), font=self.font)
        if self.statistics_error is not None:
            draw.text((8, 92), "No se pudieron leer las estadísticas",
                      fill=(255, 180, 180), font=self.font)
            draw.text((8, 110), "Revisa la conexión con MariaDB",
                      fill=(255, 255, 255), font=self.font)
        elif self.statistics_page == 0:
            self._draw_statistics_summary(draw)
        else:
            self._draw_route_performance(draw)
        draw.rectangle((0, self.height - 30, self.width, self.height),
                       fill=(0, 0, 0))
        page_label = "Resumen" if self.statistics_page == 0 else "Por ruta"
        draw.text((8, self.height - 20), page_label,
                  fill=(255, 255, 255), font=self.font)
        draw.text((self.width - 88, self.height - 20), "Cambiar >",
                  fill=(255, 255, 255), font=self.font)
        self._display_image(image, "statistics")

    def _draw_statistics_summary(self, draw: ImageDraw.ImageDraw) -> None:
        draw.text((92, 7), "Estadísticas GPS",
                  fill=(255, 255, 255), font=self.font)
        values = (
            ("Vel. máx. aprox.", f"{self.statistics.max_speed_kmh:.1f} km/h"),
            ("Vel. prom. aprox.", f"{self.statistics.average_speed_kmh:.1f} km/h"),
            ("Distancia total", f"{self.statistics.total_distance_km:.2f} km"),
            ("Ruta más larga", f"{self.statistics.longest_distance_km:.2f} km"),
        )
        card_width = (self.width - 24) // 2
        for index, (label, value) in enumerate(values):
            column = index % 2
            row = index // 2
            left = 8 + column * (card_width + 8)
            top = 36 + row * 46
            draw.rounded_rectangle(
                (left, top, left + card_width, top + 40),
                radius=5, fill=(40, 50, 65), outline=(100, 110, 125),
            )
            draw.text((left + 6, top + 3), label,
                      fill=(190, 210, 225), font=self.font)
            draw.text((left + 6, top + 17), value,
                                fill=(255, 255, 255), font=self.stats_value_font)

        draw.text((8, 130), "Distancia por ruta (km)",
                  fill=(255, 255, 255), font=self.font)
        self._draw_distance_chart(draw, top=148, bottom=self.height - 39)

    def _draw_distance_chart(
        self, draw: ImageDraw.ImageDraw, top: int, bottom: int
    ) -> None:
        routes = self.statistics.routes
        if not routes:
            draw.text((8, top + 12), "Sin recorridos finalizados",
                      fill=(190, 210, 225), font=self.font)
            return

        left, right = 28, self.width - 8
        draw.line((left, top, left, bottom), fill=(140, 150, 165))
        draw.line((left, bottom, right, bottom), fill=(140, 150, 165))
        max_distance = max(route.distance_km for route in routes) or 1.0
        slot_width = (right - left) / len(routes)
        bar_width = max(4, int(slot_width * 0.58))
        for index, route in enumerate(routes):
            bar_height = round(
                (bottom - top - 4) * route.distance_km / max_distance
            )
            center = round(left + (index + 0.5) * slot_width)
            draw.rectangle(
                (center - bar_width // 2, bottom - bar_height,
                 center + bar_width // 2, bottom - 1),
                fill=(0, 170, 130),
            )
            draw.text((center - 7, bottom + 1), str(route.route_id),
                      fill=(190, 210, 225), font=self.font)

    def _draw_route_performance(self, draw: ImageDraw.ImageDraw) -> None:
        draw.text((92, 7), "Velocidad por ruta",
                  fill=(255, 255, 255), font=self.font)
        routes = self.statistics.routes
        if not routes:
            draw.text((8, 104), "Sin recorridos finalizados",
                      fill=(190, 210, 225), font=self.font)
            return

        draw.text((20, 36), "Max", fill=(255, 170, 50), font=self.font)
        draw.text((70, 36), "Promedio", fill=(70, 180, 255), font=self.font)
        left, right, top, bottom = 32, self.width - 10, 58, self.height - 44
        draw.line((left, top, left, bottom), fill=(140, 150, 165))
        draw.line((left, bottom, right, bottom), fill=(140, 150, 165))
        max_speed = max(
            max(route.max_speed_kmh, route.average_speed_kmh)
            for route in routes
        ) or 1.0
        points_max: list[tuple[int, int]] = []
        points_average: list[tuple[int, int]] = []
        slot_width = (right - left) / max(1, len(routes) - 1)
        for index, route in enumerate(routes):
            x = (
                round(left + index * slot_width)
                if len(routes) > 1
                else (left + right) // 2
            )
            points_max.append(
                (x, round(bottom - route.max_speed_kmh / max_speed * (bottom - top)))
            )
            points_average.append(
                (x, round(bottom - route.average_speed_kmh / max_speed * (bottom - top)))
            )
            draw.text((x - 6, bottom + 3), str(route.route_id),
                      fill=(190, 210, 225), font=self.font)
        if len(points_max) > 1:
            draw.line(points_max, fill=(255, 170, 50), width=2)
            draw.line(points_average, fill=(70, 180, 255), width=2)
        for x, y in points_max:
            draw.ellipse((x - 2, y - 2, x + 2, y + 2), fill=(255, 170, 50))
        for x, y in points_average:
            draw.ellipse((x - 2, y - 2, x + 2, y + 2), fill=(70, 180, 255))

    def _render(self) -> None:
        with self.lock:
            screen = self.screen
            points = list(self.points)
            radius_index = self.radius_index
        if screen == "menu":
            self._render_menu()
            return
        if screen != "map":
            return
        if not points:
            image = Image.new("RGB", (self.width, self.height), (0, 0, 0))
            ImageDraw.Draw(image).text(
                (12, 12), "Esperando coordenadas...", fill=(255, 255, 255),
                font=self.font,
            )
            self._draw_controls(image)
            self._display_image(image, "map")
            return

        center_lat = sum(point[0] for point in points) / len(points)
        center_lon = sum(point[1] for point in points) / len(points)
        zoom = self._select_zoom(center_lat, radius_index)
        world_points = [_world_pixel(lat, lon, zoom) for lat, lon in points]
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
        radius = VIEW_RADII_M[radius_index]
        draw.text((3, self.height - 23), f"{len(pixels)} puntos | radio {radius:.0f} m",
                  fill=(255, 255, 255), font=self.font)
        draw.text((3, self.height - 12), "© OpenStreetMap contributors",
                  fill=(255, 255, 255), font=self.font)
        self._draw_controls(image)
        self._display_image(image, "map")


def create_route_display(route_database) -> Optional[RouteDisplay]:
    try:
        return RouteDisplay(route_database)
    except (ImportError, OSError, RuntimeError) as error:
        print(f"ILI9341 no disponible; se continuará sin pantalla: {error}")
        return None
