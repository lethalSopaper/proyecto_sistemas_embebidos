function createGpsRepository(pool) {
    function routeId(value) {
        const id = Number(value);
        if (!Number.isSafeInteger(id) || id < 1) {
            const error = new Error("Identificador de ruta inválido");
            error.statusCode = 400;
            throw error;
        }
        return id;
    }

    function ensureFinished(route) {
        if (!route.finished_at) {
            const error = new Error("No se pueden modificar rutas activas");
            error.statusCode = 409;
            throw error;
        }
    }

    function calculateRouteStatistics(route, points) {
        let previous = null;
        let firstCapture = null;
        let lastCapture = null;
        let maximumSpeedKmh = 0;
        let hasUntimedPoints = false;

        for (const point of points) {
            const capturedAt = point.captured_at
                ? Date.parse(point.captured_at)
                : NaN;
            const latitude = Number(point.latitude);
            const longitude = Number(point.longitude);

            if (!Number.isFinite(capturedAt)) {
                hasUntimedPoints = true;
                previous = null;
                continue;
            }

            firstCapture = firstCapture === null
                ? capturedAt
                : Math.min(firstCapture, capturedAt);
            lastCapture = lastCapture === null
                ? capturedAt
                : Math.max(lastCapture, capturedAt);

            if (previous && capturedAt > previous.capturedAt) {
                const toRadians = (degrees) => degrees * Math.PI / 180;
                const latitudeDelta = toRadians(latitude - previous.latitude);
                const longitudeDelta = toRadians(longitude - previous.longitude);
                const firstLatitude = toRadians(previous.latitude);
                const secondLatitude = toRadians(latitude);
                const haversine = Math.sin(latitudeDelta / 2) ** 2
                    + Math.cos(firstLatitude) * Math.cos(secondLatitude)
                    * Math.sin(longitudeDelta / 2) ** 2;
                const segmentMeters = 2 * 6_371_000 * Math.atan2(
                    Math.sqrt(Math.min(1, haversine)),
                    Math.sqrt(Math.max(0, 1 - haversine)),
                );
                const elapsedSeconds = (capturedAt - previous.capturedAt) / 1000;
                maximumSpeedKmh = Math.max(
                    maximumSpeedKmh,
                    segmentMeters * 3.6 / elapsedSeconds,
                );
            }
            previous = { capturedAt, latitude, longitude };
        }

        const durationSeconds = firstCapture !== null && lastCapture !== null
            ? (lastCapture - firstCapture) / 1000
            : 0;
        const averageSpeedKmh = !hasUntimedPoints && durationSeconds > 0
            ? Number(route.distance_m || 0) * 3.6 / durationSeconds
            : null;

        return {
            maximum_speed_kmh: maximumSpeedKmh,
            average_speed_kmh: averageSpeedKmh,
            duration_seconds: durationSeconds,
            has_untimed_points: hasUntimedPoints,
        };
    }

    async function getRoute(idValue) {
        const id = routeId(idValue);
        const [routes] = await pool.execute(
            `SELECT id, name,
                    DATE_FORMAT(started_at, '%Y-%m-%dT%H:%i:%s.%fZ') AS started_at,
                    DATE_FORMAT(finished_at, '%Y-%m-%dT%H:%i:%s.%fZ') AS finished_at,
                    point_count, distance_m,
                    is_valid, invalid_reason
             FROM routes WHERE id = ?`,
            [id],
        );
        if (routes.length === 0) {
            return null;
        }

        const [points] = await pool.execute(
            `SELECT DATE_FORMAT(recorded_at, '%Y-%m-%dT%H:%i:%s.%fZ') AS recorded_at,
                    DATE_FORMAT(captured_at, '%Y-%m-%dT%H:%i:%s.%fZ') AS captured_at,
                    latitude, longitude, altitude_m, satellites, hdop
             FROM route_points
             WHERE route_id = ?
             ORDER BY recorded_at, id`,
            [id],
        );
        return {
            route: routes[0],
            points,
            statistics: calculateRouteStatistics(routes[0], points),
        };
    }

    async function getExistingFinishedRoute(id) {
        const [routes] = await pool.execute(
            "SELECT id, finished_at FROM routes WHERE id = ?",
            [id],
        );
        if (routes.length === 0) {
            const error = new Error("Ruta no encontrada");
            error.statusCode = 404;
            throw error;
        }
        ensureFinished(routes[0]);
    }

    function csvCell(value) {
        const text = value === null || value === undefined ? "" : String(value);
        return `"${text.replaceAll('"', '""')}"`;
    }

    function xml(value) {
        return String(value ?? "")
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll('"', "&quot;")
            .replaceAll("'", "&apos;");
    }

    return {
        async listRoutes(filters = {}) {
            const query = String(filters.q || "").trim();
            const status = filters.status || "all";
            const sort = filters.sort || "date";
            const conditions = [];
            const parameters = [];

            if (query.length > 100) {
                const error = new Error("La búsqueda no puede superar 100 caracteres");
                error.statusCode = 400;
                throw error;
            }
            if (query) {
                conditions.push("(name LIKE ? OR CAST(id AS CHAR) LIKE ?)");
                parameters.push(`%${query}%`, `%${query}%`);
            }
            if (status === "valid") {
                conditions.push("is_valid = 1");
            } else if (status === "invalid") {
                conditions.push("is_valid = 0");
            } else if (status !== "all") {
                const error = new Error("Filtro de estado inválido");
                error.statusCode = 400;
                throw error;
            }

            const ordering = {
                date: "started_at DESC, id DESC",
                name: "name ASC, started_at DESC",
                distance: "distance_m DESC, started_at DESC",
            }[sort];
            if (!ordering) {
                const error = new Error("Orden inválido");
                error.statusCode = 400;
                throw error;
            }

            const where = conditions.length
                ? `WHERE ${conditions.join(" AND ")}`
                : "";
            const [routes] = await pool.execute(
                `SELECT id, name, started_at, finished_at, point_count, distance_m,
                        is_valid, invalid_reason
                 FROM routes ${where}
                 ORDER BY ${ordering}`,
                parameters,
            );
            return routes;
        },

        getRoute,

        async setRouteValidity(idValue, isValid, reason) {
            const id = routeId(idValue);
            if (typeof isValid !== "boolean") {
                const error = new Error("is_valid debe ser booleano");
                error.statusCode = 400;
                throw error;
            }
            const cleanReason = String(reason || "").trim();
            if (!isValid && !cleanReason) {
                const error = new Error("Indica el motivo para invalidar la ruta");
                error.statusCode = 400;
                throw error;
            }
            if (cleanReason.length > 255) {
                const error = new Error("El motivo no puede superar 255 caracteres");
                error.statusCode = 400;
                throw error;
            }
            await getExistingFinishedRoute(id);
            await pool.execute(
                "UPDATE routes SET is_valid = ?, invalid_reason = ? WHERE id = ?",
                [isValid ? 1 : 0, isValid ? null : cleanReason, id],
            );
            return getRoute(id);
        },

        async deleteRoute(idValue) {
            const id = routeId(idValue);
            await getExistingFinishedRoute(id);
            const [result] = await pool.execute(
                "DELETE FROM routes WHERE id = ? AND finished_at IS NOT NULL",
                [id],
            );
            if (result.affectedRows !== 1) {
                const error = new Error("La ruta cambió mientras se eliminaba; actualiza la lista");
                error.statusCode = 409;
                throw error;
            }
        },

        async exportCsv(idValue) {
            const data = await getRoute(idValue);
            if (!data) {
                return null;
            }
            const { route, points } = data;
            const rows = [
                ["route_id", "route_name", "started_at", "finished_at",
                    "recorded_at", "captured_at", "latitude", "longitude",
                    "altitude_m", "satellites", "hdop"],
                ...points.map((point) => [
                    route.id, route.name, route.started_at, route.finished_at,
                    point.recorded_at, point.captured_at, point.latitude,
                    point.longitude, point.altitude_m, point.satellites,
                    point.hdop,
                ]),
            ];
            return rows.map((row) => row.map(csvCell).join(",")).join("\r\n");
        },

        async exportGpx(idValue) {
            const data = await getRoute(idValue);
            if (!data) {
                return null;
            }
            const { route, points } = data;
            const trackPoints = points.map((point) => {
                const elevation = point.altitude_m === null
                    ? ""
                    : `<ele>${Number(point.altitude_m)}</ele>`;
                const time = point.captured_at || point.recorded_at;
                const timestamp = time ? `<time>${xml(time)}</time>` : "";
                return `<trkpt lat="${Number(point.latitude)}" lon="${Number(point.longitude)}">${elevation}${timestamp}</trkpt>`;
            }).join("");
            return `<?xml version="1.0" encoding="UTF-8"?>\n` +
                `<gpx version="1.1" creator="GPS Orange Pi" xmlns="http://www.topografix.com/GPX/1/1">` +
                `<trk><name>${xml(route.name || `Ruta ${route.id}`)}</name><trkseg>${trackPoints}</trkseg></trk></gpx>`;
        },
    };
}

module.exports = createGpsRepository;
