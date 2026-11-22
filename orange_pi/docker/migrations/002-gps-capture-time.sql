-- Destructive test-data migration. This removes every stored route and its
-- route_points (the foreign key cascades). Run only after confirming the
-- database contains disposable test data.
DELETE FROM routes;

ALTER TABLE routes AUTO_INCREMENT = 1;
ALTER TABLE route_points AUTO_INCREMENT = 1;
ALTER TABLE route_points
    ADD COLUMN IF NOT EXISTS captured_at DATETIME(6) NULL AFTER recorded_at;
