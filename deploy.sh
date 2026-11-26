#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ORANGE_USER="${ORANGE_USER:-orangepi}"
ORANGE_HOST="${ORANGE_HOST:-equipo12.local}"
ORANGE_PROJECT_DIR="${ORANGE_PROJECT_DIR:-/home/${ORANGE_USER}/proyecto/orange_pi}"

export ORANGE_USER ORANGE_HOST
export REMOTE_DOCKER_DIR="${REMOTE_DOCKER_DIR:-${ORANGE_PROJECT_DIR}/docker}"
export REMOTE_DIR="${REMOTE_DIR:-${ORANGE_PROJECT_DIR}/mqtt_receiver}"

"$SCRIPT_DIR/orange_pi/docker/deploy.sh"
"$SCRIPT_DIR/orange_pi/mqtt_receiver/deploy.sh"
