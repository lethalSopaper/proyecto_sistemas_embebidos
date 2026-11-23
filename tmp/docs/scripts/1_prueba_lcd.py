"""
Prueba de la pantalla ILI9341 en la Orange Pi Zero 2W

Dibuja figuras, una imagen y texto. El cuerpo es identico al de la
version para Raspberry: lo unico que cambia es este encabezado, que es
la capa de hardware.
"""

from PIL import Image, ImageDraw, ImageFont
import time

from ili9341_opi import ILI9341, color565

# Creando el objeto display
display = ILI9341(
    bus = 1,                # bus SPI1
    dispositivo = 0,        # /dev/spidev1.0
    dc = 261,               # PI5, pin 15
    cs = 229,               # PH5, pin 24: lo manejamos nosotros
    rst = 227,              # PH3, pin 13
    rotacion = 0,
    baudrate = 40000000,
)

WIDTH = display.width
HEIGHT = display.height

while True:
    display.fill(color565(200,100,0))
    display.pixel(WIDTH//2, HEIGHT//2, color565(255,0,0))

    time.sleep(1)
    display.fill_rectangle(3*WIDTH//4, 3*HEIGHT//4,100,100, color565(0,255,0))
    time.sleep(1)
    display.hline(100, 100, 200, color565(0,0,255))
    time.sleep(1)

    golden = Image.open('golden')
    golden_redim = golden.resize((240,240))
    display.image(golden_redim)
    time.sleep(1)
    
    imagen = Image.new("RGB", (WIDTH, HEIGHT))
    dibujo =  ImageDraw.Draw(imagen)
    dibujo.arc([(0,0),(240,240)],0,360, color565(0,255,0))
    display.image(imagen)

    time.sleep(1)

    FONTSIZE =24
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", FONTSIZE)
    texto = "Hola Mundo"
    dibujo.text((100,100), texto, color565(255,0,0), font)
    display.image(imagen)

    time.sleep(1)
    
