from dataclasses import dataclass
from datetime import datetime
from math import asin, cos, radians, sin, sqrt
from typing import Iterable, TypedDict


@dataclass(frozen=True)
class RoutePerformance:
    route_id: int
    name: str
    finished_at: datetime
    distance_km: float
    average_speed_kmh: float
    max_speed_kmh: float


@dataclass(frozen=True)
class RouteStatistics:
    max_speed_kmh: float
    average_speed_kmh: float
    total_distance_km: float
    longest_distance_km: float
    routes: tuple[RoutePerformance, ...]

    @classmethod
    def empty(cls) -> "RouteStatistics":
        return cls(0.0, 0.0, 0.0, 0.0, ())


class _RouteData(TypedDict):
    name: str
    finished_at: datetime
    distance_m: float
    average_speed_kmh: float
    max_speed_kmh: float


def distance_between_points(
    first: tuple[float, float], second: tuple[float, float]
) -> float:
    radius_m = 6_371_000.0
    lat1, lon1 = map(radians, first)
    lat2, lon2 = map(radians, second)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    value = (
        sin(dlat / 2) ** 2
        + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    )
    return 2 * radius_m * asin(sqrt(value))


def calculate_route_statistics(
    routes: Iterable[tuple[int, str | None, float | None, datetime, datetime]],
    points: Iterable[tuple[int, datetime, float, float]],
) -> RouteStatistics:
    route_data: dict[int, _RouteData] = {}
    total_distance_m = 0.0
    timed_distance_m = 0.0
    total_duration_s = 0.0
    longest_distance_m = 0.0

    for route_id, name, stored_distance_m, started_at, finished_at in routes:
        distance_m = max(0.0, float(stored_distance_m or 0.0))
        duration_s = (finished_at - started_at).total_seconds()
        average_speed_kmh = (
            distance_m * 3.6 / duration_s if duration_s > 0 else 0.0
        )
        route_data[route_id] = {
            "name": name or f"Ruta {route_id}",
            "finished_at": finished_at,
            "distance_m": distance_m,
            "average_speed_kmh": average_speed_kmh,
            "max_speed_kmh": 0.0,
        }
        total_distance_m += distance_m
        longest_distance_m = max(longest_distance_m, distance_m)
        if duration_s > 0:
            timed_distance_m += distance_m
            total_duration_s += duration_s

    previous_points: dict[int, tuple[datetime, float, float]] = {}
    for route_id, recorded_at, latitude, longitude in points:
        if route_id not in route_data:
            continue
        previous = previous_points.get(route_id)
        if previous is not None:
            previous_at, previous_latitude, previous_longitude = previous
            elapsed_s = (recorded_at - previous_at).total_seconds()
            if elapsed_s > 0:
                segment_m = distance_between_points(
                    (previous_latitude, previous_longitude),
                    (latitude, longitude),
                )
                route_data[route_id]["max_speed_kmh"] = max(
                    route_data[route_id]["max_speed_kmh"],
                    segment_m * 3.6 / elapsed_s,
                )
        previous_points[route_id] = (recorded_at, latitude, longitude)

    all_performance = [
        RoutePerformance(
            route_id=route_id,
            name=data["name"],
            finished_at=data["finished_at"],
            distance_km=data["distance_m"] / 1000,
            average_speed_kmh=data["average_speed_kmh"],
            max_speed_kmh=data["max_speed_kmh"],
        )
        for route_id, data in sorted(
            route_data.items(),
            key=lambda item: (item[1]["finished_at"], item[0]),
        )
    ]
    max_speed_kmh = max(
        (route.max_speed_kmh for route in all_performance), default=0.0
    )
    performance = tuple(all_performance[-8:])
    average_speed_kmh = (
        timed_distance_m * 3.6 / total_duration_s
        if total_duration_s > 0
        else 0.0
    )
    return RouteStatistics(
        max_speed_kmh=max_speed_kmh,
        average_speed_kmh=average_speed_kmh,
        total_distance_km=total_distance_m / 1000,
        longest_distance_km=longest_distance_m / 1000,
        routes=performance,
    )
