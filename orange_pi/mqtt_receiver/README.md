# Receptor MQTT de telemetría

La ESP32 publica mediciones JSON en `proyecto/gps/telemetry` usando el broker
MQTT de la Orange Pi (`equipo12.local:1883`). Este directorio contiene un
receptor mínimo para validar la conexión y el estado de carga antes de
integrarlo con Node-RED.

Instala el cliente en la Orange Pi con:

```bash
python3 -m pip install paho-mqtt
python3 receiver.py
```

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
