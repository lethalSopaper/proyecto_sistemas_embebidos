# Capa de borde: Orange Pi

Esta carpeta contiene los servicios que se ejecutarán localmente en la Orange
Pi Zero 2W para recibir, procesar y visualizar la telemetría.

- [`mqtt_receiver/`](./mqtt_receiver/): receptor MQTT, mapa OSM, pantalla
  ILI9341, controles táctiles y almacenamiento de rutas en MariaDB.
- [`python_ili9341/`](./python_ili9341/): control de la pantalla táctil.
- [`docker/`](./docker/): Mosquitto, Node-RED, InfluxDB, MariaDB y Grafana.

El receptor se despliega desde la computadora con
[`mqtt_receiver/deploy.sh`](./mqtt_receiver/deploy.sh) y se ejecuta como
servicio de usuario `systemd` en la Orange Pi.

El despliegue de Docker y sus comandos de diagnóstico están documentados en
[`docker/README.md`](./docker/README.md). Cada carga MQTT crea una ruta
identificada por fecha y hora; sus puntos se guardan en MariaDB.
