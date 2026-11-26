const assert = require("node:assert/strict");
const test = require("node:test");
const createGpsRepository = require("../gps-repository");

function createPool(resultsByQuery = []) {
    const calls = [];
    return {
        calls,
        async execute(query, parameters) {
            calls.push({ query, parameters });
            const result = resultsByQuery.find((entry) => query.includes(entry.match));
            return result ? result.result : [[], []];
        },
    };
}

test("route filters use bound search values and an allowlisted sort", async () => {
    const pool = createPool();
    const repository = createGpsRepository(pool);

    await repository.listRoutes({ q: "ruta_%", status: "invalid", sort: "distance" });

    assert.deepEqual(pool.calls[0].parameters, ["%ruta_%%", "%ruta_%%"]);
    assert.match(pool.calls[0].query, /is_valid = 0/);
    assert.match(pool.calls[0].query, /ORDER BY distance_m DESC/);
    await assert.rejects(
        repository.listRoutes({ sort: "id; DROP TABLE routes" }),
        { statusCode: 400 },
    );
});

test("invalidating a route requires a reason and only applies to finished routes", async () => {
    const pool = createPool([
        { match: "SELECT id, finished_at", result: [[{ id: 8, finished_at: null }], []] },
    ]);
    const repository = createGpsRepository(pool);

    await assert.rejects(
        repository.setRouteValidity(8, false, " "),
        { statusCode: 400 },
    );
    await assert.rejects(
        repository.setRouteValidity(8, false, "prueba"),
        { statusCode: 409 },
    );
    assert.equal(pool.calls.length, 1);
});

test("exports route points as escaped CSV and GPX", async () => {
    const route = {
        id: 7,
        name: 'Ruta "Centro"',
        started_at: "2025-01-01T10:00:00.000000Z",
        finished_at: "2025-01-01T10:05:00.000000Z",
        point_count: 1,
        distance_m: 25,
        is_valid: 1,
        invalid_reason: null,
    };
    const point = {
        recorded_at: "2025-01-01T10:00:00.000000Z",
        captured_at: "2025-01-01T10:00:00.000000Z",
        latitude: 19.4,
        longitude: -99.1,
        altitude_m: 2200,
        satellites: 8,
        hdop: 1.2,
    };
    const pool = createPool([
        { match: "FROM routes WHERE id", result: [[route], []] },
        { match: "FROM route_points", result: [[point], []] },
    ]);
    const repository = createGpsRepository(pool);

    const csv = await repository.exportCsv(7);
    const gpx = await repository.exportGpx(7);

    assert.match(csv, /"Ruta ""Centro"""/);
    assert.match(csv, /19\.4/);
    assert.match(gpx, /<name>Ruta &quot;Centro&quot;<\/name>/);
    assert.match(gpx, /<trkpt lat="19\.4" lon="-99\.1">/);
    assert.match(gpx, /<ele>2200<\/ele>/);
});

test("calculates per-route speeds from GPS capture timestamps", async () => {
    const route = {
        id: 12,
        name: "Ruta 12",
        started_at: "2025-01-01T10:00:00.000000Z",
        finished_at: "2025-01-01T10:00:10.000000Z",
        point_count: 2,
        distance_m: 111.195,
        is_valid: 1,
        invalid_reason: null,
    };
    const points = [
        {
            captured_at: "2025-01-01T10:00:00.000000Z",
            latitude: 0,
            longitude: 0,
        },
        {
            captured_at: "2025-01-01T10:00:10.000000Z",
            latitude: 0.001,
            longitude: 0,
        },
    ];
    const pool = createPool([
        { match: "FROM routes WHERE id", result: [[route], []] },
        { match: "FROM route_points", result: [points, []] },
    ]);
    const repository = createGpsRepository(pool);

    const data = await repository.getRoute(12);

    assert.ok(Math.abs(data.statistics.average_speed_kmh - 40.0302) < 0.01);
    assert.ok(Math.abs(data.statistics.maximum_speed_kmh - 40.0302) < 0.01);
    assert.equal(data.statistics.duration_seconds, 10);
    assert.equal(data.statistics.has_untimed_points, false);
});

test("marks average speed unavailable when a route has untimed samples", async () => {
    const pool = createPool([
        {
            match: "FROM routes WHERE id",
            result: [[{ id: 13, distance_m: 100 }], []],
        },
        {
            match: "FROM route_points",
            result: [[{
                captured_at: null,
                latitude: 0,
                longitude: 0,
            }], []],
        },
    ]);
    const repository = createGpsRepository(pool);

    const data = await repository.getRoute(13);

    assert.equal(data.statistics.average_speed_kmh, null);
    assert.equal(data.statistics.has_untimed_points, true);
});
