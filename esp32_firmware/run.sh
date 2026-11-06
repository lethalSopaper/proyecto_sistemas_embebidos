#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ESP_IDF_PATH="${ESP_IDF_PATH:-${IDF_PATH:-$HOME/.espressif/v6.0.2/esp-idf}}"
TARGET="esp32s3"
ACTION="${1:-build}"
PORT="${2:-${PORT:-/dev/ttyACM0}}"

echo "==========================================="
echo "        Automatizacion de ESP-IDF          "
echo "==========================================="

case "$ACTION" in
    build|flash|monitor|menuconfig)
        ;;
    *)
        echo "Uso: $0 [build|flash|monitor|menuconfig] [puerto]"
        echo
        echo "Variables opcionales:"
        echo "  ESP_IDF_PATH=/ruta/a/esp-idf"
        exit 2
        ;;
esac

cd "$SCRIPT_DIR"

release_port() {
    local port_pids
    port_pids="$(fuser "$PORT" 2>/dev/null || true)"

    if [[ -n "$port_pids" ]]; then
        echo "Liberando procesos que usan $PORT: $port_pids"
        for pid in $port_pids; do
            kill "$pid" 2>/dev/null || true
        done
        sleep 1
    fi
}

if [[ "$ACTION" == "flash" || "$ACTION" == "monitor" ]]; then
    echo "[1/3] Verificando el puerto $PORT..."
    if [[ ! -e "$PORT" ]]; then
        echo "Error: no se detecta $PORT."
        echo "Especifica otro puerto como segundo parametro:"
        echo "  $0 $ACTION /dev/ttyACM1"
        exit 1
    fi
    release_port
else
    echo "[1/2] Compilacion sin puerto serial."
fi

echo "[2/3] Cargando entorno de ESP-IDF..."
if [[ ! -f "$ESP_IDF_PATH/export.sh" ]]; then
    echo "Error: no se encontro export.sh en $ESP_IDF_PATH"
    echo "Configura ESP_IDF_PATH con la ruta de tu instalacion de ESP-IDF."
    exit 1
fi

# shellcheck disable=SC1091
source "$ESP_IDF_PATH/export.sh"

case "$ACTION" in
    build)
        echo "[3/3] Compilando desde cero para $TARGET..."
        rm -rf "$SCRIPT_DIR/build"
        idf.py set-target "$TARGET"
        idf.py build
        ;;
    flash)
        echo "[3/3] Compilando y flasheando en $PORT..."
        idf.py -p "$PORT" build flash
        ;;
    monitor)
        echo "[3/3] Abriendo monitor en $PORT..."
        idf.py -p "$PORT" monitor
        ;;
    menuconfig)
        echo "[3/3] Abriendo menuconfig..."
        idf.py menuconfig
        ;;
esac
