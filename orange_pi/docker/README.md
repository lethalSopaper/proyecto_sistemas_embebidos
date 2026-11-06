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

Configura contraseñas y el token de InfluxDB en `.env`; no compartas ni
commitees ese archivo. Si Docker muestra un error relacionado con
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
| MariaDB | Historial de rutas | Puerto interno `3306` |
| Grafana | Dashboards y visualización | `http://IP_DE_LA_ORANGE:3000` |

Obtén la dirección de la Orange Pi con:

```bash
hostname -I
```

En Grafana, el usuario inicial normalmente es `admin`; utiliza la contraseña
configurada en la primera instalación. En InfluxDB, usa el usuario, la
organización, el bucket y el token definidos en `.env`.

El esquema inicial de MariaDB se crea automáticamente en el primer arranque.
Los datos se guardan en subdirectorios de `docker/` y sobreviven a los
reinicios de los contenedores.

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
