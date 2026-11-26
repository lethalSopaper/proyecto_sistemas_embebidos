"""
Programa simple de dibujo para la pantalla tactil ili9341

Version para la Orange Pi Zero 2W. El cuerpo es identico al de la
version para Raspberry: lo unico que cambia es este encabezado, que es
la capa de hardware.
"""

import time
import numpy as np
import cv2

from ili9341_opi import ILI9341, color565
from xpt2046_opi import Touch

# Creando el objeto display para el control de la pantalla
display = ILI9341(
    bus = 1,                # bus SPI1
    dispositivo = 0,        # /dev/spidev1.0
    dc = 261,               # PI5, pin 15
    cs = 229,               # PH5, pin 24: lo manejamos nosotros
    rst = 227,              # PH3, pin 13
    rotacion = 0,
    baudrate = 40000000,
)

# Creando el objeto touch para el control del panel tactil
touch = Touch(
    bus = 1,                # /dev/spidev1.1
    dispositivo = 1,        # CS1: el panel tactil
    irq = 226,              # PH2, pin 11
    baudrate = 4000000,
)

# Limpiando la pantalla
display.fill(color565(0, 0, 0))
ancho = display.width
alto = display.height

print('Tamaño = ' , ancho, 'x', alto)

# Dibujando puntos de referencia
tam = 5
esquina_d = ((15,15),(225,15),(225,305),(15,305)) # Esquinas del cuadrado
print(esquina_d)
centros_d = [[esquina_d[i][0]+tam//2+1, esquina_d[i][1]+tam//2+1] for i in range(len(esquina_d))] # Centros

for i in range(len(esquina_d)):
    display.fill_rectangle(esquina_d[i][0], esquina_d[i][1], tam, tam, color565(255,255,255))
    display.fill_rectangle(esquina_d[i][0]+1, esquina_d[i][1]+1, tam-2, tam-2, color565(0,0,0))

# Extrayendo puntos táctiles
print('Tocar desde la esquina superior izquierda, en sentido de las manecillas del reloj')
centros_t = []
toques = 0
while toques < len(centros_d):  # Para cada punto
    if touch.is_pressed():      # Detecta primero toque
        print(touch.is_pressed())
        xv, yv = [], []         # Lista de puntos
        while touch.is_pressed():   # Acumula puntos mientras se toque
            try:
                display.fill_rectangle(0, 0, 1, 1, color565(0, 0, 0))
                xg,yg = touch.get_coordinates()
                xv.append(xg)
                yv.append(yg)
                print(xg,yg)
            except:
                pass
        x = sum(xv)//len(xv)    # Promedio de los puntos
        y = sum(yv)//len(yv)
        centros_t.append([x,y]) # Centros promedio
        display.fill_rectangle(esquina_d[toques][0], esquina_d[toques][1], tam, tam, color565(255,255,255))
        toques += 1             # Puntos tocados
        time.sleep(1)

print(centros_t)

# Obteniendo matriz homográfica o proyectiva  H
X1, Y1 = centros_d[0][0], centros_d[0][1]
X2, Y2 = centros_d[1][0], centros_d[1][1]
X3, Y3 = centros_d[2][0], centros_d[2][1]
X4, Y4 = centros_d[3][0], centros_d[3][1]

X1_t, Y1_t = centros_t[0][0], centros_t[0][1]
X2_t, Y2_t = centros_t[1][0], centros_t[1][1]
X3_t, Y3_t = centros_t[2][0], centros_t[2][1]
X4_t, Y4_t = centros_t[3][0], centros_t[3][1]

pts_reales = np.array([[X1, Y1], [X2, Y2], [X3, Y3], [X4, Y4]], dtype=np.float32)

pts_tactil = np.array([[X1_t, Y1_t], [X2_t, Y2_t], [X3_t, Y3_t], [X4_t, Y4_t]], dtype=np.float32)

H, _ = cv2.findHomography(pts_tactil, pts_reales)
print(H)
print(type(H))

# Aplicar la transformación proyectiva
def transformar_punto(x_t, y_t):
    punto = np.array([[x_t, y_t]], dtype=np.float32)
    punto_transformado = cv2.perspectiveTransform(punto.reshape(-1, 1, 2), H)
    return punto_transformado[0][0]

# Verificación
xt = 0
yt = 0
xc = 0
yc = 0

while True:
    if touch.is_pressed():
        display.fill_rectangle(xc, yc, 3, 3, color565(0, 0, 0))
        try:
            # operación dummy
            display.fill_rectangle(0, 0, 1, 1, color565(0, 0, 0))
            xt, yt = touch.get_coordinates()
        except:
            pass
        xc, yc = transformar_punto(xt, yt)
        xc, yc = round(xc), round(yc)
        print(f'Touch = ({xt},{yt}), Corregido = ({xc},{yc})')
        display.fill_rectangle(xc, yc, 3, 3, color565(255, 255, 255))

    time.sleep(0.1)
