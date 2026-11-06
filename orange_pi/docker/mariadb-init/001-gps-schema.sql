CREATE TABLE IF NOT EXISTS routes (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    device_id VARCHAR(64) NOT NULL,
    started_at DATETIME(6) NOT NULL,
    finished_at DATETIME(6) NULL,
    point_count INT UNSIGNED NOT NULL DEFAULT 0,
    distance_m DOUBLE NULL,
    PRIMARY KEY (id),
    INDEX idx_routes_device_started (device_id, started_at)
);

CREATE TABLE IF NOT EXISTS route_points (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    route_id BIGINT UNSIGNED NOT NULL,
    recorded_at DATETIME(6) NOT NULL,
    latitude DOUBLE NOT NULL,
    longitude DOUBLE NOT NULL,
    altitude_m DOUBLE NULL,
    satellites INT NULL,
    hdop DOUBLE NULL,
    PRIMARY KEY (id),
    INDEX idx_route_points_route_time (route_id, recorded_at),
    CONSTRAINT fk_route_points_route
        FOREIGN KEY (route_id) REFERENCES routes (id)
        ON DELETE CASCADE
);
