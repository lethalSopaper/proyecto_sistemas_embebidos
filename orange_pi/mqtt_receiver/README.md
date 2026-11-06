# Receptor MQTT de telemetría y ruta

La ESP32 publica mediciones JSON en `proyecto/gps/telemetry` usando el broker
MQTT de la Orange Pi (`equipo12.local:1883`). Este directorio contiene un
receptor mínimo para validar la conexión y el estado de carga antes de integrarlo con Node-RED. También dibuja la ruta recibida en el
ILI9341 conectado por SPI.

Instala el cliente en la Orange Pi con:

```bash
sudo apt update
sudo apt install mosquitto mosquitto-clients python3-venv
python3 -m venv .venv
.venv/bin/python -m pip install paho-mqtt Pillow numpy python-periphery
.venv/bin/python receiver.py
```

`numpy` es necesario porque el controlador `ili9341_opi.py` lo utiliza. Si el
entorno ya existe, instala las dependencias sin recrearlo:

```bash
.venv/bin/python -m pip install numpy python-periphery
```

El receptor usa la misma configuración de pantalla que los scripts de prueba:
SPI1 (`/dev/spidev1.0`), DC `261`, CS `229` y RESET `227`. El inicio de un
upload limpia la ruta; cada coordenada recibida se agrega sobre mosaicos de
OpenStreetMap y la línea azul representa la ruta. El punto verde es el inicio
y el rojo el último punto. La vista usa un radio de 1 km alrededor de la ruta
por defecto, muestra el número de puntos recibidos y evita que una ruta corta
se estire hasta ocupar toda la pantalla. Los mosaicos se guardan en `osm_tiles/` para reutilizarlos sin descargarlos
otra vez. La ruta actual se limpia al iniciar una nueva carga; por ahora no se
guarda un historial de rutas.

Si el panel táctil está conectado, los botones `-` y `+` de la parte superior
cambian el radio entre `50 m`, `250 m`, `1 km`, `5 km` y `10 km`. El controlador
`xpt2046_opi.py` debe estar junto a `ili9341_opi.py`; el panel usa SPI1,
`/dev/spidev1.1`, IRQ `226` y 4 MHz, igual que el script de calibración.

Puedes cambiar el radio sin modificar el código:

```bash
OSM_VIEW_RADIUS_M=250 .venv/bin/python receiver.py
```

El valor máximo es 10000 metros. Para volver a la vista recomendada:

```bash
OSM_VIEW_RADIUS_M=1000 .venv/bin/python receiver.py
```

El archivo `ili9341_opi.py` debe estar en este mismo directorio (o instalado
en el entorno Python). El error `No module named 'ili9341_opi'` significa que
el controlador usado por los scripts de prueba no fue copiado a la Orange Pi.
Desde la computadora puedes desplegarlo junto con el receptor:

```bash
ILI9341_DRIVER_DIR=/ruta/a/la/carpeta/del/controlador \
  ./orange_pi/mqtt_receiver/deploy.sh
```

La carpeta indicada debe contener `ili9341_opi.py`. Si el controlador está en
otra ubicación de la Orange Pi, cópialo al directorio del receptor:

```bash
cp /ruta/al/controlador/ili9341_opi.py \
  ~/proyecto/orange_pi/mqtt_receiver/
```

El receptor seguirá funcionando sin pantalla si el controlador no está
presente. Para desactivar explícitamente la pantalla:

```bash
ILI9341_ENABLED=0 .venv/bin/python receiver.py
```

Para comprobar las coordenadas que entrega el panel táctil, ejecuta:

```bash
TOUCH_DEBUG=1 .venv/bin/python receiver.py
```

Al tocar con la pluma, el receptor imprimirá las coordenadas crudas y las
coordenadas convertidas. El receptor usa por defecto un rango ADC de
`300..3800` para ambos ejes. Puedes corregir orientación sin editar código:

```bash
TOUCH_SWAP_AXES=1 TOUCH_INVERT_X=1 TOUCH_DEBUG=1 \
  .venv/bin/python receiver.py
```

También puedes ajustar los límites con `TOUCH_X_MIN`, `TOUCH_X_MAX`,
`TOUCH_Y_MIN` y `TOUCH_Y_MAX`. Las coordenadas convertidas deben quedar dentro
de `0..240` y `0..320`; al tocar el botón debe aparecer `Touch: zoom in` o
`Touch: zoom out`.
Las zonas táctiles incluyen un margen alrededor de cada botón para facilitar el
uso con una pluma.

La Orange Pi necesita Internet para descargar una zona que no esté en caché.
El programa usa `tile.openstreetmap.org`, envía un User-Agent identificable y
muestra la atribución requerida en la pantalla. Respeta el uso moderado del
servicio; para recorridos frecuentes conviene configurar un servidor de
mosaicos propio o precargar el área.

Para probar solo MQTT sin inicializar la pantalla:

```bash
ILI9341_ENABLED=0 .venv/bin/python receiver.py
```

## Configuración completa

Conecta la Orange Pi y la ESP32 a la misma red WiFi de 2.4 GHz. Obtén la IP
de la Orange Pi:

```bash
hostname -I
```

Configura Mosquitto para aceptar al ESP32 desde la red local:

```bash
sudo tee /etc/mosquitto/conf.d/gps.conf >/dev/null <<'EOF'
listener 1883 0.0.0.0
allow_anonymous true
EOF
sudo systemctl enable --now mosquitto
sudo systemctl restart mosquitto
```

Configura e inicia Mosquitto:

```bash
sudo systemctl enable --now mosquitto
```

En el ESP32, ejecuta `./run.sh menuconfig` dentro de `esp32_firmware` y usa:

```text
MQTT broker URI: mqtt://IP_DE_LA_ORANGE_PI:1883
MQTT telemetry topic: proyecto/gps/telemetry
```

El SSID y la contraseña deben corresponder a la red 2.4 GHz. Cuando el ESP32
publique, este receptor mostrará los estados `uploading` y `complete`, además
de las coordenadas recibidas.

## Despliegue desde la computadora

Desde la raíz del repositorio, ejecuta:

```bash
./orange_pi/mqtt_receiver/deploy.sh
```

El script usa por defecto:

- Usuario: `orangepi`
- Host: `equipo12.local`
- Destino: `~/proyecto/orange_pi/mqtt_receiver`

Después del despliegue, el receptor queda iniciado automáticamente como
servicio de usuario.

Puedes cambiar los valores sin editar el script:

```bash
ORANGE_HOST=192.168.1.50 ./orange_pi/mqtt_receiver/deploy.sh
```

## Inicio automático como servicio de usuario

El despliegue instala y habilita `proyecto-gps-receiver.service` como servicio
del usuario `orangepi`, no como servicio del sistema. También habilita el
*linger* de ese usuario para que el receptor arranque aunque no haya una
sesión gráfica iniciada. Desde la computadora ejecuta:

```bash
./orange_pi/mqtt_receiver/deploy.sh
```

El receptor se iniciará automáticamente después de que esté disponible la red
y se reiniciará si termina inesperadamente. Para revisar el servicio:

```bash
ssh orangepi@equipo12.local \
  'systemctl --user status proyecto-gps-receiver.service'
```

Para seguir los mensajes del receptor:

```bash
ssh orangepi@equipo12.local \
  'journalctl --user -u proyecto-gps-receiver.service -f'
```

Para detenerlo temporalmente y ejecutarlo manualmente:

```bash
ssh orangepi@equipo12.local \
  'systemctl --user stop proyecto-gps-receiver.service'
```

Después de detenerlo, puedes iniciarlo otra vez con:

```bash
ssh orangepi@equipo12.local \
  'systemctl --user start proyecto-gps-receiver.service'
```
