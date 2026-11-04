# Firmware de la ESP32-S3 XIAO

Proyecto de ESP-IDF para la capa de campo. La aplicación principal llama a la
fuente seleccionada en [`main/source.h`](./main/source.h).

## Contenido previsto

- Inicialización del GPS y lectura de coordenadas.
- Conexión WiFi y publicación de telemetría mediante MQTT.
- Control de LED, buzzer y otros actuadores.
- Configuración de compilación y carga del firmware.

La lógica principal se organiza en [`main/`](./main/), mientras que cada fuente
se guarda dentro de [`source/`](./source/), al mismo nivel.

## Fuente actual: GPS NEO-6M + OLED SSD1306

La fuente [`2_gps_neo6m_oled/`](./source/2_gps_neo6m_oled/) lee tramas NMEA
`GGA` mediante UART a 9600 baudios y muestra por el monitor serial la latitud,
longitud, altitud, número de satélites y HDOP cuando existe un fix válido.
Los mismos datos se muestran en el OLED SSD1306 de 128x64.
La lectura se sincroniza con el carácter inicial `$` de cada trama NMEA para
descartar fragmentos recibidos durante el arranque.

Conexión inicial usando los GPIO configurados en el código:

| NEO-6M | ESP32-S3 XIAO |
|---|---|
| TX | D1 / GPIO2 |
| RX | D2 / GPIO3 |
| GND | GND |
| VCC | 3.3V |

El GPS debe compartir GND con la ESP32. Verifica el voltaje de alimentación del
módulo antes de conectarlo. La conexión del OLED es:

| OLED | ESP32-S3 XIAO |
|---|---|
| SDA | D8 / GPIO7 |
| SCL | D7 / GPIO44 |
| VCC | 3.3V |
| GND | GND |

La fuente utiliza la dirección I2C `0x3C` del OLED (formato U8g2 `0x78`).
D4/GPIO5 y D5/GPIO6 no se utilizan.
El proyecto usa la API I2C nueva de ESP-IDF 6 mediante el HAL local de U8g2.

## Compilar y flashear

Desde este directorio, con el entorno de ESP-IDF habilitado:

```bash
./run.sh build
./run.sh flash
./run.sh monitor
./run.sh menuconfig
```

Usa `./run.sh menuconfig` para configurar el SSID, la contraseña WiFi, el
broker MQTT y el tópico sin cargar manualmente el entorno de ESP-IDF.

`run.sh` usa `/dev/ttyACM0` por defecto. Si la placa aparece en otro puerto,
indícalo como segundo parámetro:

```bash
./run.sh flash /dev/ttyACM1
./run.sh monitor /dev/ttyACM1
```

El script busca ESP-IDF en `~/.espressif/v6.0.2/esp-idf`. Si la instalación
está en otra ubicación, usa `ESP_IDF_PATH=/ruta/a/esp-idf ./run.sh build`.

Para cambiar de fuente, modifica [`main/source.h`](./main/source.h):
descomenta el encabezado y la macro `SOURCE` correspondientes, y comenta los
de la fuente anterior. CMake compila las fuentes disponibles, pero solo se
ejecuta la función seleccionada por `SOURCE`.

## Fuente GPS + botón + MQTT

La fuente `3_gps_neo6m_oled_mqtt` usa el botón en D0/GPIO1 conectado a GND
(pull-up interno). Al presionarlo alterna entre monitoreo GPS y carga MQTT.
Cada pulsación cambia el modo una sola vez; no es necesario mantener el botón
presionado. En modo de carga, la pantalla conserva el estado de la conexión y
una segunda pulsación regresa al monitoreo GPS.
Configura SSID, contraseña, broker y tópico con `idf.py menuconfig`, en
`GPS telemetry`. El valor predeterminado del broker es
`mqtt://equipo12.local:1883` y el tópico es `proyecto/gps/telemetry`.

La Orange Pi debe ejecutar un broker MQTT en el puerto 1883 y puede validar
los mensajes con [`orange_pi/mqtt_receiver/receiver.py`](../orange_pi/mqtt_receiver/receiver.py).
