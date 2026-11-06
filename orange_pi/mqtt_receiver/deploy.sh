#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ORANGE_USER="${ORANGE_USER:-orangepi}"
ORANGE_HOST="${ORANGE_HOST:-equipo12.local}"
REMOTE_DIR="${REMOTE_DIR:-/home/${ORANGE_USER}/proyecto/orange_pi/mqtt_receiver}"
REMOTE="${ORANGE_USER}@${ORANGE_HOST}"
ILI9341_DRIVER_DIR="${ILI9341_DRIVER_DIR:-}"
TOUCH_DRIVER_DIR="${TOUCH_DRIVER_DIR:-$ILI9341_DRIVER_DIR}"

echo "Desplegando receptor MQTT en ${REMOTE}:${REMOTE_DIR}"

ssh "$REMOTE" "mkdir -p '$REMOTE_DIR'"
scp "$SCRIPT_DIR/receiver.py" "$SCRIPT_DIR/route_display.py" "$SCRIPT_DIR/README.md" "$REMOTE:$REMOTE_DIR/"
if [[ -n "$ILI9341_DRIVER_DIR" ]]; then
    scp "$ILI9341_DRIVER_DIR/ili9341_opi.py" "$REMOTE:$REMOTE_DIR/"
fi
if [[ -n "$TOUCH_DRIVER_DIR" && -f "$TOUCH_DRIVER_DIR/xpt2046_opi.py" ]]; then
    scp "$TOUCH_DRIVER_DIR/xpt2046_opi.py" "$REMOTE:$REMOTE_DIR/"
fi

ssh "$REMOTE" "cd '$REMOTE_DIR' && \
    python3 -m venv .venv && \
    .venv/bin/python -m pip install --upgrade pip paho-mqtt Pillow numpy python-periphery"

echo
echo "Despliegue completado."
echo "Para iniciar el receptor:"
echo "  ssh $REMOTE 'cd $REMOTE_DIR && .venv/bin/python receiver.py'"
