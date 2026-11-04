import json
import os

import paho.mqtt.client as mqtt

BROKER = os.getenv("MQTT_BROKER", "0.0.0.0")
PORT = int(os.getenv("MQTT_PORT", "1883"))
TOPIC = os.getenv("MQTT_TOPIC", "proyecto/gps/telemetry")
STATUS_TOPIC = f"{TOPIC}/status"


def on_connect(client, userdata, flags, reason_code, properties=None):
    if reason_code != 0:
        raise RuntimeError(f"MQTT connection failed: {reason_code}")
    client.subscribe(TOPIC, qos=1)
    client.subscribe(STATUS_TOPIC, qos=1)
    print(f"Connected. Listening on {TOPIC} and {STATUS_TOPIC}")


def on_message(client, userdata, message):
    if message.topic == STATUS_TOPIC:
        print(f"ESP32 status: {message.payload.decode('utf-8')}")
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


client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_connect = on_connect
client.on_message = on_message
client.connect(BROKER, PORT, 60)
client.loop_forever()
