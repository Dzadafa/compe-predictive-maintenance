from flask import Flask, request, jsonify, render_template
import paho.mqtt.client as mqtt
import threading, json, time
from collections import deque
from additions import format_duration, parse_duration
import os, json
# from pyngrok import ngrok

app = Flask(__name__)

# ---- Data storage ----
MAX_HISTORY = 20
latest_data = {}  

# -- Countdown default times handler --
DEFAULTS_FILE = "countdown_defaults.json"

if os.path.exists(DEFAULTS_FILE):
    with open(DEFAULTS_FILE, "r") as f:
        device_defaults = json.load(f)
else:
    device_defaults = {}

def save_defaults():
    with open(DEFAULTS_FILE, "w") as f:
        json.dump(device_defaults, f)

DEFAULT_COUNTDOWN = 60 * 60 * 24 * 7  # example: 1 week in seconds
devices_countdown = {}

def update_device_timer(device_id):
    now = time.time()
    if device_id not in devices_countdown:
        devices_countdown[device_id] = {"remaining": DEFAULT_COUNTDOWN, "last_update": now}
    else:
        elapsed = now - devices_countdown[device_id]["last_update"]
        devices_countdown[device_id]["remaining"] -= int(elapsed)
        devices_countdown[device_id]["last_update"] = now
        if devices_countdown[device_id]["remaining"] < 0:
            devices_countdown[device_id]["remaining"] = 0

# ---- MQTT ----
mqtt_broker = "broker.emqx.io"
# mqtt_broker = "192.168.1.110"
mqtt_port = 1883


# default subscriptions
DEFAULT_TOPICS = [f"Pompa{i}/Vibration/#" for i in range(1, 6)]

def on_connect(client, userdata, flags, rc):
    print("connected:", rc)
    for topic in DEFAULT_TOPICS:
        client.subscribe(topic)
        print("Subscribed to:", topic)


def on_message(client, userdata, msg):
    try:
        topic_parts = msg.topic.split("/")
        if len(topic_parts) < 3:
            print("Invalid topic format:", msg.topic)
            return

        # Base topic = "PompaN/Vibration"
        base_topic = "/".join(topic_parts[:2])

        # Field name = rest of the path after base
        field_parts = topic_parts[2:]
        field = "_".join(part.lower() for part in field_parts)

        # Init device entry if needed
        if base_topic not in latest_data:
            latest_data[base_topic] = {}
            update_device_timer(base_topic)

        latest_data[base_topic]["last_seen"] = time.time()

        payload = msg.payload.decode()
        try:
            payload = int(payload) if field == "kategori" else float(payload)
        except ValueError:
            pass

        if field not in latest_data[base_topic]:
            latest_data[base_topic][field] = deque(maxlen=MAX_HISTORY)

        latest_data[base_topic][field].append(payload)

    except Exception as e:
        print("error parsing mqtt:", e)


def mqtt_loop():
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(mqtt_broker, mqtt_port, 60)
    client.loop_forever()

threading.Thread(target=mqtt_loop, daemon=True).start()

# ---- Routes ----
@app.route("/")
def home():
    return "<h2>Go to <a href='/dashboard'>/dashboard</a> or <a href='/plot'>/plot</a></h2>"

@app.route("/the3d")
def deez3():
    return render_template("3d-page.html")

@app.route("/dashboard")
def dashboard():
    device_id = request.args.get("device", default=0, type=int)
    return render_template("index.html", device=device_id)

@app.route("/cd-page")
def cd_page():
    device_id = request.args.get("device", default=0, type=int)
    return render_template("countdown.html", device=device_id)

@app.route("/plot")
def plot():
    device_id = request.args.get("device", default=0, type=int)
    return render_template("plot.html", device=device_id)

@app.route("/data")
def data():
    device_id = request.args.get("device", default=0, type=int)
    devices = sorted(latest_data.keys())
    if not devices:
        return jsonify({"error": "No devices online"})

    if device_id < 0 or device_id >= len(devices):
        device_id = 0

    device_topic = devices[device_id]
    latest = {
        f: (v[-1] if isinstance(v, deque) else v)
        for f, v in latest_data[device_topic].items()
    }
    return jsonify({"device": device_topic, **latest})

@app.route("/devices")
def devices_list():
    now = time.time()
    devices = []

    # Only allow Pompa1–Pompa5
    allowed_devices = [f"Pompa{i}" for i in range(1, 6)]

    for dev, fields in latest_data.items():
        clean_name = dev.split("/")[0]

        if clean_name not in allowed_devices:
            continue  # skip unknown devices

        last_seen = fields.get("last_seen", 0)
        online = (now - last_seen) < 10  # 10s threshold

        devices.append({"name": clean_name, "online": online})

    return jsonify(devices)


# ---- Countdown routes ----
@app.route("/get_countdown/<int:device_id>")
def get_countdown(device_id):
    devices = sorted(latest_data.keys())
    if device_id < 0 or device_id >= len(devices):
        return jsonify({"error": "invalid device id"}), 404

    topic = devices[device_id]
    update_device_timer(topic)
    return jsonify({
        "remaining": devices_countdown[topic]["remaining"],
        "pretty": format_duration(devices_countdown[topic]["remaining"])
    })

@app.route("/reset_countdown/<int:device_id>", methods=["POST"])
def reset_countdown(device_id):
    devices = sorted(latest_data.keys())
    if device_id < 0 or device_id >= len(devices):
        return jsonify({"error": "invalid device id"}), 404

    topic = devices[device_id]
    default = device_defaults.get(topic, DEFAULT_COUNTDOWN)  # use topic, not id
    devices_countdown[topic] = {"remaining": default, "last_update": time.time()}
    return jsonify({"status": "reset", "remaining": default})

@app.route("/countdown/<int:device_id>/set", methods=["POST"])
def set_countdown(device_id):
    try:
        devices = sorted(latest_data.keys())
        if device_id < 0 or device_id >= len(devices):
            return jsonify({"error": "invalid device id"}), 404

        topic = devices[device_id]

        data = request.get_json(force=True)
        text = data.get("value", "")
        seconds = parse_duration(text, DEFAULT_COUNTDOWN) if text else DEFAULT_COUNTDOWN

        devices_countdown[topic] = {"remaining": seconds, "last_update": time.time()}
        device_defaults[topic] = seconds  # save as new default
        save_defaults()

        return jsonify({"status": "ok", "remaining": seconds})
    except Exception as e:
        print("Error in set_countdown:", e)
        return jsonify({"error": str(e)}), 500
# --- End of countdown Route ---

if __name__ == "__main__":
    app.run(port=5000)

