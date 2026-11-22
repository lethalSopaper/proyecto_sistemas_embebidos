# Servicios de la Orange Pi

Este directorio contiene `docker-compose.yml` y la configuración de los
servicios de la capa de borde:

- Eclipse Mosquitto para MQTT.
- Node-RED para respaldar telemetría y administrar rutas.
- InfluxDB para conservar muestras GPS.
- MariaDB para el historial de rutas.
- Grafana para consultar y visualizar los datos.

## Iniciar los servicios

Desde la Orange Pi, entra a este directorio, no a `mqtt_receiver`:

```bash
cd ~/proyecto/orange_pi/docker
test -f .env || cp .env.example .env
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
| Node-RED | Panel de rutas y respaldo MQTT | `http://IP_DE_LA_ORANGE:1880/routes` |
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
`route_points` almacena sus coordenadas, hora de recepción (`recorded_at`),
hora UTC de captura GPS (`captured_at`), altitud, satélites y HDOP. El receptor
Python usa el puerto `3306` para guardar el historial.

El dashboard muestra la distancia acumulada y la ruta más larga usando
recorridos finalizados. Las velocidades máxima y promedio usan la hora UTC de
captura GPS de cada muestra. `recorded_at` se conserva como hora de recepción
para diagnóstico.

### Node-RED, gestión de rutas y telemetría

Agrega estas variables a tu `.env` actual; no reemplaces el archivo ni uses
las contraseñas de ejemplo en una instalación real:

```dotenv
NODERED_ADMIN_USER=admin
NODERED_ADMIN_PASSWORD=elige-una-clave-segura
NODERED_HTTP_USER=admin
NODERED_HTTP_PASSWORD=elige-otra-clave-segura
```

El editor de Node-RED (`:1880/`) usa las credenciales `NODERED_ADMIN_*`. El
panel de rutas (`:1880/routes`) y sus API usan `NODERED_HTTP_*`. La
autenticación HTTP se aplica al panel y a todos los endpoints del flujo.
Node-RED sirve HTTP sin TLS; mantenlo dentro de una red de confianza o VPN y
no reenvíes el puerto `1880` directamente a Internet.

El panel permite:

1. Buscar rutas por nombre o ID y filtrar por válidas/inválidas.
2. Consultar puntos y una representación SVG del recorrido.
3. Marcar una ruta finalizada como inválida con motivo, o restaurarla.
4. Eliminar permanentemente una ruta finalizada y sus puntos después de
   confirmar la acción.
5. Descargar el recorrido como CSV o GPX.

Las rutas inválidas permanecen en MariaDB para permitir su revisión y
restauración, pero se excluyen de las estadísticas de rendimiento. La columna
`is_valid` se agrega mediante la migración idempotente
`migrations/003-route-validity.sql`.

Node-RED se suscribe al mismo tópico que el receptor Python y guarda las
muestras en InfluxDB con la hora de captura GPS. El dashboard provisionado se
abre en
`http://IP_DE_LA_ORANGE:3000/d/gps-telemetry/telemetria-gps`; presenta altitud,
satélites, HDOP y coordenadas de las últimas 24 horas. El bucket configurado
por `INFLUXDB_BUCKET` se usa como bucket predeterminado de Grafana.

InfluxDB está en la misma Orange Pi: puede conservar telemetría cuando
MariaDB no está disponible, pero no protege contra la falla o pérdida del
almacenamiento de toda la Orange Pi. Tampoco reconstruye automáticamente las
rutas de MariaDB; la ruta y la visualización histórica siguen dependiendo del
receptor Python y MariaDB. Si InfluxDB no está disponible, Node-RED registra
el error en sus logs; no existe una cola local de reintento para esos fallos.

Desde la raíz del repositorio, el despliegue completo es:

```bash
ORANGE_HOST=192.168.1.158 ./deploy.sh
```

El script usa SSH/SCP, actualiza solamente los archivos de configuración
versionados, aplica la migración aditiva y reconstruye Node-RED. No copia `.env`
ni reemplaza los directorios persistentes. Antes de combinar los flujos nuevos,
Node-RED guarda una copia del archivo de flujos existente con el sufijo
`flows.json.gps-backup-*`. El usuario debe tener permiso de escritura en el
volumen `docker/nodered` para que Node-RED pueda guardar su flujo y esa copia.

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
SELECT recorded_at, captured_at, latitude, longitude, altitude_m, satellites, hdop
FROM route_points
WHERE route_id = 1
ORDER BY recorded_at;
```
