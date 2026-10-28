# Rastreador de Rutas (GPS Route Tracker)

## 1. Planteamiento del Problema

Los deportistas (como ciclistas, corredores o patinadores) requieren monitorear constantemente sus trayectos, velocidades y distancias para evaluar su rendimiento físico. Sin embargo, los dispositivos comerciales de rastreo suelen ser costosos, cerrados, y no siempre permiten exportar los datos crudos para un análisis personalizado. Se requiere diseñar un sistema de telemetría y monitoreo accesible que registre las coordenadas de la ruta, almacene el historial de entrenamientos y ofrezca una visualización detallada (mapas y gráficas) utilizando una arquitectura distribuida entre el borde y un servidor central.

## 2. Arquitectura del Proyecto

El sistema sigue un flujo de datos basado en tres capas de operación:

### Capa de Campo (Adquisición de Datos)

*   **Microcontrolador:** Seeed Studio XIAO ESP32-S3. Actuará como el nodo móvil que el deportista llevará consigo.
*   **Sensor:** Módulo GPS (como un NEO-8M) conectado a la ESP32 para adquirir latitud, longitud y altitud.
*   **Actuador:** Un pequeño *buzzer* o un LED que reciba comandos para notificar al usuario sobre el estado del sistema (por ejemplo, confirmación de conexión WiFi o fijación de satélites).
*   **Comunicación:** La ESP32 recopilará los datos y, al estar en rango de red, los transmitirá utilizando el protocolo **MQTT** vía WiFi hacia la capa de borde.

### Capa de Borde (Procesamiento y Control Local)

*   **Hardware:** Orange Pi Zero 2W, funcionando como el servidor local (Base Station).
*   **Contenedores Docker (Locales):**
    *   **Mosquitto:** Broker MQTT que recibe el flujo de coordenadas y métricas desde la ESP32.
    *   **Node-RED:** Se encargará de suscribirse a los tópicos de Mosquitto, procesar los datos de las rutas y redistribuirlos a las bases de datos.
    *   **InfluxDB:** Base de datos temporal orientada a series de tiempo para el flujo rápido de datos.
*   **Interfaz Gráfica Local:** Se ejecutará un programa en **Python** dentro de la Orange Pi para controlar una **pantalla táctil ILI9341**. Esta pantalla servirá como panel de control físico, mostrando un menú para visualizar el estado del servidor, estadísticas del último recorrido, y enviar comandos de control hacia la ESP32 (flujo inverso).

### Capa de Interfaz (Visualización y Almacenamiento Pesado)

Para asegurar la fluidez del sistema y no saturar la Orange Pi Zero 2W, esta capa se alojará en una PC.
*   **Hardware:** PC ejecutando contenedores Docker.
*   **Almacenamiento (MariaDB):** Base de datos relacional para guardar el registro histórico de todas las rutas, perfiles de usuario y sesiones de entrenamiento de forma permanente. (Alimentada desde el Node-RED de la Orange Pi).
*   **Visualización (Grafana):** Se conectará a las bases de datos para desplegar un *dashboard* interactivo. Utilizará paneles de tipo *Geomap* (OpenStreetMap) para trazar visualmente la ruta GPS recorrida, acompañado de gráficas de velocidad, tiempo y elevación.