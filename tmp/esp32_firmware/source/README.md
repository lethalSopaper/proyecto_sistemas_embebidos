# Fuentes de la ESP32

Cada subdirectorio contiene una fuente independiente. La fuente funcional
actual es `3_gps_neo6m_oled_mqtt`, que integra GPS NEO-6M, OLED SSD1306, botón,
WiFi con perfiles persistentes, MQTT y almacenamiento temporal en NVS. Para
seleccionar cuál
se ejecuta, importa su encabezado en [`../main/source.h`](../main/source.h) y
asigna su función de entrada a `SOURCE`.
