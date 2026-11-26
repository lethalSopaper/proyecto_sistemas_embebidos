---
title: "Rastreador de Rutas y Rendimiento Deportivo"
subtitle: "Proyecto Final"
author: '`\textbf{Equipo 12:}\\ \textbullet~Tepal Briseño Hansel Yael \\ \textbullet~Ugartechea González Luis Antonio `{=latex}'
date: "28 de octubre de 2026"
institute: "Fundamentos de Sistemas Embebidos 2027-1 | Prof. Eduardo Fragoso Navarro"
theme: "metropolis"
---

## Planteamiento del Problema

- **Contexto:** Deportistas (ciclistas, corredores) necesitan monitorear trayectos, distancias y velocidad.
- **Problema:** Dispositivos comerciales cerrados, costosos y de difícil acceso a los datos crudos.
- **Solución Propuesta:**
  - Sistema de telemetría GPS abierto y distribuido.
  - Hardware de bajo costo (ESP32 + Orange Pi).
  - Almacenamiento histórico y visualización personalizada en tiempo real.

## Arquitectura General del Sistema

El proyecto se divide en tres capas fundamentales, cumpliendo con el esquema IoT:

1. **Capa de Campo:** Adquisición de datos y movilidad.
2. **Capa de Borde:** Procesamiento local, broker y control de interfaz física.
3. **Capa de Interfaz (PC):** Almacenamiento pesado y visualización avanzada de datos.

## Capa de Campo (Móvil)

- **Microcontrolador:** ESP32-S3 XIAO (Portátil y de bajo consumo).
- **Sensor:** Módulo GPS (ej. NEO-8M) para captura de latitud, longitud y altitud.
- **Actuador:** LED/Buzzer para notificaciones de estado (ej. satélites fijados).
- **Etapa de Potencia:** Transistor MOSFET/NPN para accionar el actuador de forma segura.
- **Comunicación:** Transmisión de datos vía WiFi mediante **MQTT**.

## Capa de Borde (Estación Local)

**Hardware:** Orange Pi Zero 2W

- **Contenedores Docker Local:**
  - `Mosquitto:` Recibe los datos de la ESP32.
  - `Node-RED:` Procesa los flujos, enruta datos y ejecuta el script de control.
  - `InfluxDB:` Base de datos temporal para métricas recientes.
- **Interfaz Física:**
  - Pantalla táctil **ILI9341** controlada por un script de Python.
  - *Nota:* El script de Python es disparado directamente desde Node-RED.

## Capa de Interfaz (Servidor Central)

Para evitar saturar la Orange Pi y asegurar fluidez, esta capa se aloja en una **PC**.

- **Contenedores Docker en PC:**
  - `MariaDB:` Almacenamiento histórico relacional de todas las rutas y sesiones.
  - `Grafana:` Dashboard principal de usuario.
- **Visualización:**
  - Mapas (OpenStreetMap) para el trazo de la ruta.
  - Gráficas de altimetría y velocidad.

## Flujo de Datos

**Flujo Directo (Telemetría):**
`Sensor GPS` $\rightarrow$ `ESP32` $\rightarrow$ `MQTT` $\rightarrow$ `Node-RED` $\rightarrow$ `Bases de Datos` $\rightarrow$ `Grafana / Pantalla`

**Flujo Inverso (Control):**
`Pantalla (Python) / Node-RED` $\rightarrow$ `MQTT` $\rightarrow$ `ESP32` $\rightarrow$ `Actuador (Buzzer)`

<!-- ## Cronograma y Siguientes Pasos

- **Semana 1:** Proyecto y planeación $\rightarrow$ *(Completado)*
- **Semana 2 (Primer Avance):** Pruebas de adquisición GPS en ESP32 y broker MQTT.
- **Semana 3 (Segundo Avance):** Implementación de Capa de Borde (Node-RED + Pantalla ILI9341).
- **Semana 4 (Tercer Avance):** Configuración de PC (MariaDB + Grafana).
- **Semana 5:** Pruebas de integración, análisis de consumo energético y entrega final.

## Preguntas y Comentarios

\begin{center}
\Large ¡Gracias por su atención!
\end{center} -->