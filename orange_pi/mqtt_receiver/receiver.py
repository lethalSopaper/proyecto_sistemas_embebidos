import json
import os

import paho.mqtt.client as mqtt

if os.getenv("ILI9341_ENABLED", "1") == "1":
    try:
        from route_display import create_route_display
    except ImportError as error:
        print(f"ILI9341 no disponible; se continuará sin pantalla: {error}")
        create_route_display = None
else:
    create_route_display = None

BROKER = os.getenv("MQTT_BROKER", "0.0.0.0")
PORT = int(os.getenv("MQTT_PORT", "1883"))
TOPIC = os.getenv("MQTT_TOPIC", "proyecto/gps/telemetry")
STATUS_TOPIC = f"{TOPIC}/status"
route_display = create_route_display() if create_route_display is not None else None


def on_connect(client, userdata, flags, reason_code, properties=None):
    if reason_code != 0:
        raise RuntimeError(f"MQTT connection failed: {reason_code}")
    client.subscribe(TOPIC, qos=1)
    client.subscribe(STATUS_TOPIC, qos=1)
    print(f"Connected. Listening on {TOPIC} and {STATUS_TOPIC}")


def on_message(client, userdata, message):
    if message.topic == STATUS_TOPIC:
        status = message.payload.decode("utf-8")
        if status == "uploading" and route_display is not None:
            route_display.clear()
        print(f"ESP32 status: {status}")
        return
    try:
        measurement = json.loads(message.payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        print(f"Invalid telemetry payload: {error}")
        return
    print(
        "GPS: "
        f"lat={measurement['latitude']:.6f} "
        f"lon={measurement['longitude']:.6f} "
        f"alt={measurement['altitude']:.1f} m"
    )
    if route_display is not None:
        route_display.add_point(measurement["latitude"], measurement["longitude"])


client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_connect = on_connect
client.on_message = on_message
client.connect(BROKER, PORT, 60)
client.loop_forever()
