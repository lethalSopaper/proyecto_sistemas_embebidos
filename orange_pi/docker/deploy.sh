#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ORANGE_USER="${ORANGE_USER:-orangepi}"
ORANGE_HOST="${ORANGE_HOST:-equipo12.local}"
REMOTE="${ORANGE_USER}@${ORANGE_HOST}"
REMOTE_DOCKER_DIR="${REMOTE_DOCKER_DIR:-/home/${ORANGE_USER}/proyecto/orange_pi/docker}"
REMOTE_STAGE="/tmp/proyecto-gps-deploy-${USER:-user}-$$"

echo "Preparando despliegue de servicios en ${REMOTE}:${REMOTE_DOCKER_DIR}"
ssh "$REMOTE" "mkdir -p '$REMOTE_STAGE'"
scp -r "$SCRIPT_DIR/docker-compose.yml" "$SCRIPT_DIR/README.md" \
    "$SCRIPT_DIR/nodered-config" "$SCRIPT_DIR/grafana/dashboards" \
    "$SCRIPT_DIR/grafana/provisioning" "$SCRIPT_DIR/mariadb-init" \
    "$SCRIPT_DIR/migrations" "$SCRIPT_DIR/deploy-remote.sh" \
    "$REMOTE:$REMOTE_STAGE/"

ssh -t "$REMOTE" \
    "sudo bash '$REMOTE_STAGE/deploy-remote.sh' '$REMOTE_STAGE' '$REMOTE_DOCKER_DIR'"

echo
echo "Despliegue de Docker completado. No se modificaron .env ni los datos persistentes."
