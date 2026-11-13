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
scp "$SCRIPT_DIR/receiver.py" "$SCRIPT_DIR/route_display.py" \
    "$SCRIPT_DIR/route_database.py" "$SCRIPT_DIR/README.md" \
    "$SCRIPT_DIR/proyecto-gps-receiver.service" "$SCRIPT_DIR/.env.example" \
    "$REMOTE:$REMOTE_DIR/"
if [[ -n "$ILI9341_DRIVER_DIR" ]]; then
    scp "$ILI9341_DRIVER_DIR/ili9341_opi.py" "$REMOTE:$REMOTE_DIR/"
fi
if [[ -n "$TOUCH_DRIVER_DIR" && -f "$TOUCH_DRIVER_DIR/xpt2046_opi.py" ]]; then
    scp "$TOUCH_DRIVER_DIR/xpt2046_opi.py" "$REMOTE:$REMOTE_DIR/"
fi

ssh -t "$REMOTE" "cd '$REMOTE_DIR' && \
    python3 -m venv .venv && \
    .venv/bin/python -m pip install --upgrade pip paho-mqtt Pillow numpy \
        python-periphery mysql-connector-python && \
    mkdir -p ~/.config/systemd/user && \
    sed 's|%h/proyecto/orange_pi/mqtt_receiver|$REMOTE_DIR|g' \
        proyecto-gps-receiver.service > \
        ~/.config/systemd/user/proyecto-gps-receiver.service && \
    chmod 0644 ~/.config/systemd/user/proyecto-gps-receiver.service && \
    sudo systemctl disable --now proyecto-gps-receiver.service 2>/dev/null || true; \
    sudo rm -f /etc/systemd/system/proyecto-gps-receiver.service; \
    systemctl --user daemon-reload && \
    systemctl --user enable --now proyecto-gps-receiver.service && \
    sudo loginctl enable-linger '$ORANGE_USER'"

echo
echo "Despliegue completado."
echo "El receptor quedó habilitado como servicio del usuario y arrancará con la Orange Pi."
echo "Para consultar su estado:"
echo "  ssh $REMOTE 'systemctl --user status proyecto-gps-receiver.service'"
echo "Para ver sus logs:"
echo "  ssh $REMOTE 'journalctl --user -u proyecto-gps-receiver.service -f'"
