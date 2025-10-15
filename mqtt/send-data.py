import paho.mqtt.client as mqtt
import time
import random
import sys
import math
import datetime

BROKER = "broker.emqx.io"
PORT = 1883

# Get args
is_broken = "--broken" in sys.argv

# Get device number
try:
    device_num = next((int(arg) for arg in sys.argv[1:] if arg.isdigit()), 1)
except ValueError:
    print("Error: Device number must be an integer.")
    sys.exit(1)

DEVICE_TOPIC = f"Pompa{device_num}/Vibration"

client = mqtt.Client()
client.connect(BROKER, PORT, 60)

print(f"Publisher started for Device #{device_num} ({'BROKEN' if is_broken else 'NORMAL'})")

while True:
    if is_broken:
        # simulate higher vibration (unsatisfactory → unacceptable)
        x = round(random.uniform(-5, 5), 2)
        y = round(random.uniform(-5, 5), 2)
        z = round(random.uniform(-5, 5), 2)
    else:
        # normal range
        x = round(random.uniform(-1, 1), 2)
        y = round(random.uniform(-1, 1), 2)
        z = round(random.uniform(-1, 1), 2)

    rms = round(math.sqrt(x**2 + y**2 + z**2), 3)

    if 0.28 <= rms <= 1.12:
        kategori = 1  # Good (Green)
    elif 1.12 < rms <= 2.80:
        kategori = 2  # Satisfactory (Yellow)
    elif 2.80 < rms <= 7.10:
        kategori = 3  # Unsatisfactory (Orange)
    elif rms > 7.10:
        kategori = 4  # Unacceptable (Red)
    else:
        kategori = 0  # Below threshold


    # timestamp = datetime.datetime.utcnow()
    # plus_23_days = timestamp + datetime.timedelta(days=29)
    # formatted = plus_23_days.strftime('%Y-%m-%dT%H:%M:%SZ')
    #
    timestamp = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')

    client.publish(f"{DEVICE_TOPIC}/Velocity/X", x)
    client.publish(f"{DEVICE_TOPIC}/Velocity/Y", y)
    client.publish(f"{DEVICE_TOPIC}/Velocity/Z", z)
    client.publish(f"{DEVICE_TOPIC}/RMS", rms)
    client.publish(f"{DEVICE_TOPIC}/Kategori", kategori)
    client.publish(f"{DEVICE_TOPIC}/timestamp", timestamp)
    # client.publish(f"{DEVICE_TOPIC}/timestamp", formatted)

    print(f"[PUB] {DEVICE_TOPIC}: X={x}, Y={y}, Z={z}, RMS={rms}, Kategori={kategori}")

    time.sleep(2)

