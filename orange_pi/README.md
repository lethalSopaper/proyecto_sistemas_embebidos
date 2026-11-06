# Capa de borde: Orange Pi

Esta carpeta contiene los servicios que se ejecutarán localmente en la Orange
Pi Zero 2W para recibir, procesar y visualizar la telemetría.

- [`mqtt_receiver/`](./mqtt_receiver/): receptor MQTT, mapa OSM, pantalla
  ILI9341 y controles táctiles.
- [`python_ili9341/`](./python_ili9341/): control de la pantalla táctil.
- [`docker/`](./docker/): servicios de Mosquitto, Node-RED e InfluxDB.

El receptor se despliega desde la computadora con
[`mqtt_receiver/deploy.sh`](./mqtt_receiver/deploy.sh) y se ejecuta como
servicio de usuario `systemd` en la Orange Pi.
