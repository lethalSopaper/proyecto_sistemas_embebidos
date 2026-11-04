# Receptor MQTT de telemetría

La ESP32 publica mediciones JSON en `proyecto/gps/telemetry` usando el broker
MQTT de la Orange Pi (`equipo12.local:1883`). Este directorio contiene un
receptor mínimo para validar la conexión y el estado de carga antes de
integrarlo con Node-RED.

Instala el cliente en la Orange Pi con:

```bash
sudo apt update
sudo apt install mosquitto mosquitto-clients python3-venv
python3 -m venv .venv
.venv/bin/python -m pip install paho-mqtt
.venv/bin/python receiver.py
```

## Configuración completa

Conecta la Orange Pi y la ESP32 a la misma red WiFi de 2.4 GHz. Obtén la IP
de la Orange Pi:

```bash
hostname -I
```

Configura Mosquitto para aceptar al ESP32 desde la red local:

```bash
sudo tee /etc/mosquitto/conf.d/gps.conf >/dev/null <<'EOF'
listener 1883 0.0.0.0
allow_anonymous true
EOF
sudo systemctl enable --now mosquitto
sudo systemctl restart mosquitto
```

Inicia el receptor:

```bash
cd ~/proyecto/orange_pi/mqtt_receiver
.venv/bin/python receiver.py
```

En el ESP32, ejecuta `./run.sh menuconfig` dentro de `esp32_firmware` y usa:

```text
MQTT broker URI: mqtt://IP_DE_LA_ORANGE_PI:1883
MQTT telemetry topic: proyecto/gps/telemetry
```

El SSID y la contraseña deben corresponder a la red 2.4 GHz. Cuando el ESP32
publique, este receptor mostrará los estados `uploading` y `complete`, además
de las coordenadas recibidas.

## Despliegue desde la computadora

Desde la raíz del repositorio, ejecuta:

```bash
./orange_pi/mqtt_receiver/deploy.sh
```

El script usa por defecto:

- Usuario: `orangepi`
- Host: `equipo12.local`
- Destino: `~/proyecto/orange_pi/mqtt_receiver`

Después del despliegue, inicia el receptor con:

```bash
ssh orangepi@equipo12.local \
  'cd ~/proyecto/orange_pi/mqtt_receiver && .venv/bin/python receiver.py'
```

Puedes cambiar los valores sin editar el script:

```bash
ORANGE_HOST=192.168.1.50 ./orange_pi/mqtt_receiver/deploy.sh
```
