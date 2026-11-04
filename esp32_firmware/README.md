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

## Práctica actual: GPS NEO-6M

La fuente [`1_gps_neo6m/`](./source/1_gps_neo6m/) lee tramas NMEA
`GGA` mediante UART a 9600 baudios y muestra por el monitor serial la latitud,
longitud, altitud, número de satélites y HDOP cuando existe un fix válido.
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
módulo antes de conectarlo. Los pines D7/GPIO44 y D8/GPIO7 quedan reservados
para el OLED; D4/GPIO5 y D5/GPIO6 no se utilizan.

## Compilar y flashear

Desde este directorio, con el entorno de ESP-IDF habilitado:

```bash
./run.sh build
./run.sh flash
./run.sh monitor
```

`run.sh` usa `/dev/ttyACM0` por defecto. Si la placa aparece en otro puerto,
indícalo como segundo parámetro:

```bash
./run.sh flash /dev/ttyACM1
./run.sh monitor /dev/ttyACM1
```

El script busca ESP-IDF en `~/.espressif/v6.0.2/esp-idf`. Si la instalación
está en otra ubicación, usa `ESP_IDF_PATH=/ruta/a/esp-idf ./run.sh build`.

Para cambiar de fuente, modifica únicamente la macro `SOURCE` en
[`main/source.h`](./main/source.h), dejando seleccionada una sola
función de entrada.
