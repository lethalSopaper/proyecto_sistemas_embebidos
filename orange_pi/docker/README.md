# Servicios de la Orange Pi

Este directorio contiene `docker-compose.yml` y la configuración de los
servicios de la capa de borde:

- Eclipse Mosquitto para MQTT.
- Node-RED para procesar y enrutar mensajes.
- InfluxDB para almacenar datos recientes.
- MariaDB para el historial de rutas.
- Grafana para consultar y visualizar los datos.

## Iniciar los servicios

Desde la Orange Pi, entra a este directorio, no a `mqtt_receiver`:

```bash
cd ~/proyecto/orange_pi/docker
cp .env.example .env
nano .env
```

Configura las contraseñas y el token de InfluxDB en `.env`; no compartas ni
commitees ese archivo. `GRAFANA_ADMIN_PASSWORD` debe coincidir con la
contraseña actual del administrador si Grafana ya se inicializó; cambiar la
variable no modifica una contraseña guardada en el volumen existente. Si Docker
muestra un error relacionado con
`apparmor_parser`, instala las herramientas de AppArmor:

```bash
sudo apt update
sudo apt install apparmor apparmor-utils
echo 'export PATH="$PATH:/usr/sbin:/sbin"' >> ~/.bashrc
source ~/.bashrc
```

Inicia los servicios con:

```bash
sudo docker-compose up -d
sudo docker-compose ps
```

La arquitectura levantada es:

| Servicio | Función | Acceso |
|---|---|---|
| Mosquitto | Broker MQTT para la ESP32 | Puerto `1883` |
| Node-RED | Procesamiento y distribución | `http://IP_DE_LA_ORANGE:1880` |
| InfluxDB | Telemetría reciente | `http://IP_DE_LA_ORANGE:8086` |
| MariaDB | Historial de rutas | Puerto `3306` |
| Grafana | Dashboards y visualización | `http://IP_DE_LA_ORANGE:3000` |

Obtén la dirección de la Orange Pi con:

```bash
hostname -I
```

Abre el dashboard provisionado en
`http://IP_DE_LA_ORANGE:3000/d/gps-stats/estadisticas-gps`. El datasource
`MariaDB GPS` se configura automáticamente para leer las rutas finalizadas. En
Grafana, inicia sesión con `GRAFANA_ADMIN_USER` y `GRAFANA_ADMIN_PASSWORD` de
`.env`. En InfluxDB, usa el usuario, la organización, el bucket y el token
definidos allí.
Para aplicar esta configuración a una instalación existente, agrega esas dos
variables de Grafana a `.env` sin reemplazar las contraseñas que ya utilizas y
recrea el servicio:

```bash
sudo docker-compose up -d grafana
```

El esquema inicial de MariaDB se crea automáticamente en el primer arranque.
Los datos se guardan en subdirectorios de `docker/` y sobreviven a los
reinicios de los contenedores. La tabla `routes` identifica cada carga y
`route_points` almacena sus coordenadas, fecha/hora, altitud, satélites y HDOP.
El receptor Python usa el puerto `3306` para guardar el historial.

El dashboard muestra la distancia acumulada y la ruta más larga usando
recorridos finalizados. También muestra velocidades aproximadas: la máxima usa
el intervalo entre mensajes recibidos y la promedio divide la distancia entre
la duración de la carga MQTT. No representan la velocidad real del recorrido;
el firmware actual no incluye la hora de captura GPS de cada muestra.

## Operación y diagnóstico

Ver el estado:

```bash
sudo docker-compose ps
```

Ver los logs de todos los servicios o de uno específico:

```bash
sudo docker-compose logs --tail=80
sudo docker-compose logs --tail=80 grafana
```

Reiniciar los servicios:

```bash
sudo docker-compose restart
```

Detenerlos sin borrar los datos:

```bash
sudo docker-compose down
```

No uses `docker-compose down -v` salvo que quieras eliminar los volúmenes de
Docker. Las carpetas `grafana/`, `influxdb/`, `mariadb/`, `mosquitto/` y
`nodered/` contienen datos persistentes.

Si Grafana queda en `Restarting` y sus logs indican que
`/var/lib/grafana` no tiene permisos de escritura:

```bash
sudo docker-compose stop grafana
sudo chown -R 472:472 grafana
sudo chmod -R u+rwX grafana
sudo docker-compose up -d grafana
```

El servicio Mosquitto instalado directamente en el sistema no debe ejecutarse
al mismo tiempo que el contenedor, porque ambos usan el puerto `1883`:

```bash
sudo systemctl disable --now mosquitto
```

El receptor MQTT se despliega desde la computadora con:

```bash
./orange_pi/mqtt_receiver/deploy.sh
```

Después crea `~/proyecto/orange_pi/mqtt_receiver/.env` a partir de
`.env.example` y coloca en `GPS_DB_PASSWORD` el mismo valor de
`MARIADB_PASSWORD` usado por MariaDB. El servicio de usuario espera y reintenta
la conexión si MariaDB todavía está iniciando.

## Consultas para probar la base de datos

Ingresar a la base de datos con:

```bash
cd ~/proyecto/orange_pi/docker
sudo docker-compose exec mariadb mariadb -u gps_user -p gps
```

probar el registro de los datos del gps:

```sql
SELECT id, name, started_at, finished_at, point_count, distance_m
FROM routes
ORDER BY started_at DESC;
```

```sql
SELECT recorded_at, latitude, longitude, altitude_m, satellites, hdop
FROM route_points
WHERE route_id = 1
ORDER BY recorded_at;
```
