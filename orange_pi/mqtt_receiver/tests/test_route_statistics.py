import unittest
from datetime import datetime, timedelta

from route_statistics import calculate_route_statistics


class RouteStatisticsTests(unittest.TestCase):
    def test_calculates_overall_and_per_route_metrics(self):
        start = datetime(2026, 1, 1, 12, 0)
        routes = [
            (1, "Ruta 1", 1000.0, start, start + timedelta(hours=1)),
            (
                2,
                "Ruta 2",
                2000.0,
                start + timedelta(hours=1),
                start + timedelta(hours=3),
            ),
        ]
        points = [
            (1, start, 0.0, 0.0),
            (1, start + timedelta(seconds=100), 0.0, 0.0001),
            (2, start + timedelta(hours=1), 0.0, 0.0),
            (2, start + timedelta(hours=1, seconds=10), 0.001, 0.0),
            (2, start + timedelta(hours=1, seconds=200), 0.001, 0.0),
        ]

        statistics = calculate_route_statistics(routes, points)

        self.assertAlmostEqual(statistics.max_speed_kmh, 40.0, delta=0.2)
        self.assertAlmostEqual(statistics.average_speed_kmh, 36.0, places=5)
        self.assertEqual(statistics.total_distance_km, 3.0)
        self.assertEqual(statistics.longest_distance_km, 2.0)
        self.assertEqual(len(statistics.routes), 2)
        self.assertAlmostEqual(
            statistics.routes[1].average_speed_kmh, 36.0, places=5
        )

    def test_history_keeps_routes_outside_recent_chart_window(self):
        start = datetime(2026, 1, 1)
        routes = [
            (
                route_id,
                None,
                100.0,
                start + timedelta(days=route_id),
                start + timedelta(days=route_id, seconds=20),
            )
            for route_id in range(1, 11)
        ]
        points = [
            (1, start + timedelta(days=1), 0.0, 0.0),
            (1, start + timedelta(days=1, seconds=10), 0.001, 0.0),
        ]

        statistics = calculate_route_statistics(routes, points)

        self.assertEqual(len(statistics.routes), 10)
        self.assertEqual(
            [route.route_id for route in statistics.routes[-8:]],
            list(range(3, 11)),
        )
        self.assertGreater(statistics.max_speed_kmh, 30.0)

    def test_empty_history_returns_zeroes(self):
        statistics = calculate_route_statistics([], [])

        self.assertEqual(statistics.max_speed_kmh, 0.0)
        self.assertEqual(statistics.average_speed_kmh, 0.0)
        self.assertEqual(statistics.total_distance_km, 0.0)
        self.assertEqual(statistics.longest_distance_km, 0.0)
        self.assertEqual(statistics.routes, ())

    def test_zero_duration_and_duplicate_point_times_do_not_create_speed(self):
        recorded_at = datetime(2026, 1, 1)
        routes = [(1, "Ruta 1", 500.0, recorded_at, recorded_at)]
        points = [
            (1, recorded_at, 0.0, 0.0),
            (1, recorded_at, 1.0, 1.0),
        ]

        statistics = calculate_route_statistics(routes, points)

        self.assertEqual(statistics.max_speed_kmh, 0.0)
        self.assertEqual(statistics.average_speed_kmh, 0.0)

    def test_untimed_legacy_points_are_not_used_for_velocity(self):
        start = datetime(2026, 1, 1)
        routes = [(1, "Ruta 1", 100.0, start, start + timedelta(seconds=20))]
        points = [
            (1, None, 0.0, 0.0),
            (1, start, 0.0, 0.0),
            (1, start + timedelta(seconds=10), 0.001, 0.0),
        ]

        statistics = calculate_route_statistics(routes, points)

        self.assertAlmostEqual(statistics.max_speed_kmh, 40.0, delta=0.2)
        self.assertEqual(statistics.average_speed_kmh, 0.0)


if __name__ == "__main__":
    unittest.main()
