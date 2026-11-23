"""
Puntos rebotando en la pantalla ILI9341, en la Orange Pi Zero 2W

El cuerpo es identico al de la version para Raspberry: lo unico que
cambia es este encabezado, que es la capa de hardware.
"""

from PIL import Image, ImageDraw, ImageFont
import time
from random import randint, random

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

class punto():
    def __init__(self,x,y,vx,vy,color):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.color = color
    def mueve(self):
        display.fill_rectangle(int(self.x), int(self.y), 3, 3, color565(0,0,0))
        self.x += self.vx
        self.y += self.vy
        if (self.x > WIDTH) or (self.x < 0):
            self.vx = -self.vx
        if (self.y > HEIGHT) or (self.y < 0):
            self.vy = -self.vy
        display.fill_rectangle(int(self.x), int(self.y), 3, 3, self.color)

puntos = []
for i in range(5):
    r,g,b = randint(0,255), randint(0,255), randint(0,255)
    puntos.append(punto(0,0,0.2*random(),0.2*random(), color565(r,g,b)))

display.fill(color565(0,0,0))
while True:
    for i in range(len(puntos)):
        puntos[i].mueve()


