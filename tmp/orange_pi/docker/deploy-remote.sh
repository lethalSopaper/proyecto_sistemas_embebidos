#!/usr/bin/env bash
set -euo pipefail

stage="$1"
destination="$2"

cleanup() {
    rm -rf -- "$stage"
}
trap cleanup EXIT

install -d "$destination"
install -m 0644 "$stage/docker-compose.yml" "$destination/docker-compose.yml"
install -m 0644 "$stage/README.md" "$destination/README.md"
for directory in nodered-config mariadb-init migrations; do
    install -d "$destination/$directory"
    cp -a "$stage/$directory/." "$destination/$directory/"
done
for directory in dashboards provisioning; do
    install -d "$destination/grafana/$directory"
    cp -a "$stage/$directory/." "$destination/grafana/$directory/"
done

cd "$destination"
compose() { docker-compose "$@"; }

compose config >/dev/null
compose up -d mariadb
ready=false
for attempt in $(seq 1 60); do
    if compose exec -T mariadb sh -ec \
        'mariadb-admin ping -uroot -p"$MARIADB_ROOT_PASSWORD" --silent' \
        >/dev/null 2>&1; then
        ready=true
        break
    fi
    sleep 2
done
if [ "$ready" != true ]; then
    echo "MariaDB no estuvo listo después de 120 segundos" >&2
    exit 1
fi
compose exec -T mariadb sh -ec \
    'mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" "$MARIADB_DATABASE"' \
    < "$destination/migrations/003-route-validity.sql"
compose up -d --build nodered grafana
compose ps
