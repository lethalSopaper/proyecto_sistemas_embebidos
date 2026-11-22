# Node-RED

La configuración desplegable vive en
[`orange_pi/docker/nodered-config/`](../orange_pi/docker/nodered-config/).
El despliegue construye una imagen de Node-RED que:

- Se suscribe a `proyecto/gps/telemetry` y escribe cada muestra en el bucket de
  InfluxDB usando `captured_at_ms` como timestamp.
- Expone el panel de administración de rutas en `/routes`, protegido por
  autenticación HTTP.
- Permite buscar/filtrar rutas, revisar sus puntos en un mapa esquemático,
  invalidarlas o restaurarlas, eliminarlas con confirmación y exportarlas a
  CSV o GPX.

El flujo se combina de forma idempotente con el archivo de flujos existente en
el volumen de Node-RED. Antes de cambiarlo se crea una copia
`flows.json.gps-backup-*`; no se reemplazan los archivos de usuario ni los
datos guardados en `/data`.
