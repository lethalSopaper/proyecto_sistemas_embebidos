# Rastreador de Rutas y Rendimiento Deportivo (GPS Route Tracker)

Este repositorio contiene el código fuente, esquemáticos y configuraciones para el Proyecto Final de la materia **Fundamentos de Sistemas Embebidos (2027-1)**.

El proyecto consiste en un sistema distribuido de telemetría GPS para deportistas, utilizando una arquitectura IoT de tres capas (Campo, Borde e Interfaz) para adquirir, procesar, visualizar y almacenar datos de geolocalización y rendimiento.

## Planteamiento del Problema
Los deportistas requieren monitorear constantemente sus trayectos y distancias. Este proyecto propone un sistema accesible que registra las coordenadas de la ruta de forma portátil, transmite los datos mediante MQTT a una estación base local y ofrece una visualización detallada en tiempo real mediante pantallas físicas y dashboards web.

## Arquitectura del Sistema

El proyecto está dividido en tres capas principales:

1. **Capa de Campo (Adquisición de datos móvil):**
   - **Microcontrolador:** ESP32-S3 XIAO.
   - **Sensores:** Módulo GPS (ej. NEO-8M) para obtener latitud, longitud y altitud.
   - **Actuadores:** LED/Buzzer con **etapa de potencia** (Transistor NPN/MOSFET) para notificaciones de estado (Flujo inverso).
   - **Energía:** Sistema portátil con batería LiPo y módulo de carga.
   - **Comunicación:** Envío de datos vía WiFi utilizando el protocolo **MQTT**.

2. **Capa de Borde (Procesamiento Local):**
   - **Hardware:** Orange Pi Zero 2W.
   - **Software (Contenedores Docker):**
     - `Eclipse Mosquitto`: Broker MQTT.
     - `Node-RED`: Procesamiento de datos y enrutamiento. Ejecuta el script de Python.
     - `InfluxDB`: Base de datos de series de tiempo para datos recientes.
   - **Interfaz Física:** Pantalla táctil **ILI9341** controlada mediante un script de **Python** (ejecutado desde Node-RED) para visualizar métricas en tiempo real y enviar comandos de control a la ESP32.

3. **Capa de Interfaz (Almacenamiento y Visualización Pesada):**
   - **Hardware:** PC Central.
   - **Software (Contenedores Docker):**
     - `MariaDB`: Base de datos relacional para el registro histórico de todas las rutas y usuarios.
     - `Grafana`: Dashboards interactivos con mapas (OpenStreetMap) y gráficas de velocidad/elevación.

## Estructura del Repositorio

Se sugiere mantener la siguiente estructura para organizar los archivos del proyecto:

```text
├── esp32_firmware/         # Código C++/Arduino para la ESP32-S3 XIAO
│   └── main/               # Lógica de GPS, MQTT y control de actuadores
├── orange_pi/              # Scripts y configuraciones para la Capa de Borde
│   ├── python_ili9341/     # Script de Python para controlar la pantalla táctil
│   └── docker/             # Archivo docker-compose.yml (Mosquitto, Node-RED, InfluxDB)
├── pc_server/              # Configuraciones para la PC (Capa de Interfaz)
│   └── docker/             # Archivo docker-compose.yml (MariaDB, Grafana)
├── node_red/               # Archivos JSON exportados de los flujos de Node-RED
├── docs/                   # Documentación, diagramas (Fritzing/Kicad), imágenes
└── README.md               # Este archivo
```

## Tecnologías y Herramientas

* **Lenguajes:** C++ (ESP32), Python (Orange Pi).
* **Bases de Datos:** InfluxDB, MariaDB.
* **Visualización e Integración:** Node-RED, Grafana, Open Maps.
* **Infraestructura:** Docker, Docker Compose.
* **Protocolos:** MQTT, I2C/SPI (para pantalla y sensores).

## Instalación y Uso (Próximamente)

*Las instrucciones detalladas para levantar los contenedores Docker, flashear la ESP32 y configurar la pantalla se añadirán conforme avance el desarrollo.*

---
*Desarrollado para la clase del Profesor Eduardo Fragoso Navarro.*