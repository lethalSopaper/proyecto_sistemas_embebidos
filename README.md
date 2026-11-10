# Rastreador de Rutas y Rendimiento Deportivo (GPS Route Tracker)

Este repositorio contiene el código fuente, esquemáticos y configuraciones para el Proyecto Final de la materia **Fundamentos de Sistemas Embebidos (2027-1)**.

El proyecto consiste en un sistema distribuido de telemetría GPS para deportistas, utilizando una arquitectura IoT de tres capas (Campo, Borde e Interfaz) para adquirir, procesar, visualizar y almacenar datos de geolocalización y rendimiento.

## Planteamiento del Problema
Los deportistas requieren monitorear constantemente sus trayectos y distancias. Este proyecto propone un sistema accesible que registra las coordenadas de la ruta de forma portátil, transmite los datos mediante MQTT a una estación base local y ofrece una visualización detallada en tiempo real mediante pantallas físicas y dashboards web.

## Estado actual

Actualmente está implementado el flujo principal ESP32 → MQTT → Orange Pi:

- La ESP32 obtiene coordenadas del GPS NEO-6M y las almacena temporalmente para
  cargarlas por MQTT. Hay variantes con OLED y con LEDs.
- La Orange Pi recibe la telemetría, dibuja la ruta sobre OpenStreetMap y
  conserva las rutas en MariaDB con fecha, puntos y distancia aproximada.
- Mosquitto, Node-RED, InfluxDB, MariaDB y Grafana se ejecutan en Docker en la
  Orange Pi.
- El receptor MQTT se instala como servicio de usuario y arranca
  automáticamente al encender la Orange Pi.

Node-RED todavía debe configurarse para distribuir la telemetría hacia
InfluxDB, MariaDB y el programa de pantalla. La pantalla muestra la ruta
actual; el historial completo queda en MariaDB.

## Arquitectura del Sistema

El proyecto está dividido en tres capas principales:

1. **Capa de Campo (Adquisición de datos móvil):**
   - **Microcontrolador:** ESP32-S3 XIAO.
   - **Sensores:** Módulo GPS NEO-6M para obtener latitud, longitud y altitud.
   - **Actuadores:** LED/Buzzer con **etapa de potencia** (Transistor NPN/MOSFET) para notificaciones de estado (Flujo inverso).
   - **Energía:** Sistema portátil con batería LiPo y módulo de carga.
   - **Comunicación:** Envío de datos vía WiFi utilizando el protocolo **MQTT**.

2. **Capa de Borde (Procesamiento Local):**
   - **Hardware:** Orange Pi Zero 2W.
   - **Software en Docker:**
     - `Eclipse Mosquitto`: Broker MQTT.
     - `Node-RED`: Procesamiento y distribución.
     - `InfluxDB`: Telemetría reciente.
     - `MariaDB`: Historial de rutas.
     - `Grafana`: Visualización.
   - **Receptor Python:** guarda las rutas y controla la pantalla ILI9341.
   - **Interfaz Física:** Pantalla táctil **ILI9341** para visualizar rutas y
     controles de zoom.

3. **Capa de Interfaz:**
   - **Hardware:** PC o navegador conectado a la Orange Pi.
   - **Software:** Acceso remoto a Grafana y Node-RED alojados en la Orange Pi.

## Estructura del Repositorio

Se sugiere mantener la siguiente estructura para organizar los archivos del proyecto:

```text
├── esp32_firmware/         # Proyecto ESP-IDF para la ESP32-S3 XIAO
│   ├── main/               # Punto de entrada y selector de fuentes
│   └── source/             # Código de cada fuente de la ESP32
├── orange_pi/              # Scripts y configuraciones para la Capa de Borde
│   ├── mqtt_receiver/      # Receptor, pantalla y base de datos de rutas
│   ├── python_ili9341/     # Controlador de la pantalla táctil
│   └── docker/             # Mosquitto, Node-RED, InfluxDB, MariaDB y Grafana
├── pc_server/              # Configuraciones opcionales para la PC
├── node_red/               # Archivos JSON exportados de los flujos de Node-RED
├── docs/                   # Documentación, diagramas (Fritzing/Kicad), imágenes
└── README.md               # Este archivo
```

## Tecnologías y Herramientas

* **Lenguajes:** C con ESP-IDF (ESP32), Python (Orange Pi).
* **Bases de Datos:** InfluxDB, MariaDB.
* **Visualización e Integración:** Node-RED, Grafana, Open Maps.
* **Infraestructura:** Docker, Docker Compose.
* **Protocolos:** MQTT, I2C/SPI (para pantalla y sensores).

## Inicio rápido

Consulta [`esp32_firmware/README.md`](./esp32_firmware/README.md) para
configurar, compilar y flashear la ESP32. Para desplegar el receptor y su
servicio automático en la Orange Pi:

```bash
./orange_pi/mqtt_receiver/deploy.sh
```

La configuración específica del receptor está en
[`orange_pi/mqtt_receiver/README.md`](./orange_pi/mqtt_receiver/README.md).

---
*Desarrollado para la clase del Profesor Eduardo Fragoso Navarro.*