import math
import os
import threading
import time
from datetime import datetime, timezone

import mysql.connector
from mysql.connector import Error


class RouteDatabase:
    def __init__(self) -> None:
        self.connection = self._connect_with_retry()
        self.route_id: int | None = None
        self.point_count = 0
        self.distance_m = 0.0
        self.previous_point: tuple[float, float] | None = None
        self.lock = threading.RLock()
        self._ensure_route_name()

    def _ensure_route_name(self) -> None:
        cursor = self.connection.cursor()
        try:
            cursor.execute(
                "ALTER TABLE routes ADD COLUMN name VARCHAR(128) NULL"
            )
            self.connection.commit()
        except Error as error:
            if error.errno != 1060:
                raise
        cursor.execute(
            """
            UPDATE routes
            SET name = CONCAT('Ruta ', DATE_FORMAT(started_at, '%Y-%m-%d %H:%i'))
            WHERE name IS NULL OR name = ''
            """
        )
        self.connection.commit()
        cursor.close()

    @staticmethod
    def _connect_with_retry():
        config = {
            "host": os.getenv("GPS_DB_HOST", "127.0.0.1"),
            "port": int(os.getenv("GPS_DB_PORT", "3306")),
            "user": os.getenv("GPS_DB_USER", "gps_user"),
            "password": os.environ["GPS_DB_PASSWORD"],
            "database": os.getenv("GPS_DB_NAME", "gps"),
        }
        retry_seconds = int(os.getenv("GPS_DB_RETRY_SECONDS", "5"))
        while True:
            try:
                connection = mysql.connector.connect(**config)
                print("Conectado a MariaDB para guardar rutas", flush=True)
                return connection
            except Error as error:
                print(
                    f"MariaDB no disponible ({error}); reintentando en "
                    f"{retry_seconds} s",
                    flush=True,
                )
                time.sleep(retry_seconds)

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc).replace(tzinfo=None)

    @staticmethod
    def _distance_m(
        first: tuple[float, float], second: tuple[float, float]
    ) -> float:
        radius_m = 6_371_000.0
        lat1, lon1 = map(math.radians, first)
        lat2, lon2 = map(math.radians, second)
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        value = (
            math.sin(dlat / 2) ** 2
            + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        )
        return 2 * radius_m * math.asin(math.sqrt(value))

    def start_route(self) -> None:
        with self.lock:
            if self.route_id is not None:
                self.finish_route()
            started_at = self._now()
            cursor = self.connection.cursor()
            cursor.execute(
                """
                INSERT INTO routes (name, device_id, started_at)
                VALUES (%s, %s, %s)
                """,
                (
                    f"Ruta {started_at:%Y-%m-%d %H:%M}",
                    os.getenv("GPS_DEVICE_ID", "esp32-gps"),
                    started_at,
                ),
            )
            self.connection.commit()
            self.route_id = cursor.lastrowid
            cursor.close()
            self.point_count = 0
            self.distance_m = 0.0
            self.previous_point = None
        print(f"Ruta iniciada: id={self.route_id}", flush=True)

    def add_point(self, measurement: dict[str, object]) -> None:
        with self.lock:
            if self.route_id is None:
                print("Telemetría recibida sin una ruta activa; se descarta", flush=True)
                return
            latitude = float(measurement["latitude"])
            longitude = float(measurement["longitude"])
            point = (latitude, longitude)
            if self.previous_point is not None:
                self.distance_m += self._distance_m(self.previous_point, point)
            cursor = self.connection.cursor()
            cursor.execute(
            """
            INSERT INTO route_points
                (route_id, recorded_at, latitude, longitude, altitude_m,
                 satellites, hdop)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
                (
                    self.route_id,
                    self._now(),
                    latitude,
                    longitude,
                    measurement.get("altitude"),
                    measurement.get("satellites"),
                    measurement.get("hdop"),
                ),
            )
            self.point_count += 1
            cursor.execute(
            """
            UPDATE routes
            SET point_count = %s, distance_m = %s
            WHERE id = %s
            """,
                (self.point_count, self.distance_m, self.route_id),
            )
            self.connection.commit()
            cursor.close()
            self.previous_point = point

    def finish_route(self) -> None:
        with self.lock:
            if self.route_id is None:
                return
            cursor = self.connection.cursor()
            cursor.execute(
            """
            UPDATE routes
            SET finished_at = %s, point_count = %s, distance_m = %s
            WHERE id = %s
            """,
                (self._now(), self.point_count, self.distance_m, self.route_id),
            )
            self.connection.commit()
            cursor.close()
            print(
            f"Ruta finalizada: id={self.route_id}, puntos={self.point_count}, "
            f"distancia={self.distance_m:.1f} m",
            flush=True,
            )
            self.route_id = None
            self.previous_point = None

    def list_routes(self, sort_by: str = "date") -> list[dict[str, object]]:
        order = "started_at DESC" if sort_by == "date" else "name ASC, started_at DESC"
        with self.lock:
            cursor = self.connection.cursor(dictionary=True)
            cursor.execute(
                f"""
                SELECT id, name, started_at, finished_at, point_count, distance_m
                FROM routes
                ORDER BY {order}
                """
            )
            routes = cursor.fetchall()
            cursor.close()
            return list(routes)

    def get_route_points(self, route_id: int) -> list[tuple[float, float]]:
        with self.lock:
            cursor = self.connection.cursor()
            cursor.execute(
                """
                SELECT latitude, longitude
                FROM route_points
                WHERE route_id = %s
                ORDER BY recorded_at, id
                """,
                (route_id,),
            )
            points = [(float(latitude), float(longitude)) for latitude, longitude in cursor]
            cursor.close()
            return points
