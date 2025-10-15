from flask import Flask, request, jsonify, render_template
import paho.mqtt.client as mqtt
import threading, json, time
from collections import deque
from additions import format_duration, parse_duration
import os, json
import datetime
from dateutil.parser import isoparse

app = Flask(__name__)

# ---- Data storage ----
MAX_HISTORY = 20
latest_data = {}

# -- Countdown Persistency --
DEFAULTS_FILE = "countdown_defaults.json"
COUNTDOWN_STATE_FILE = "countdown_state.json" 

# Load countdown defaults
if os.path.exists(DEFAULTS_FILE):
    with open(DEFAULTS_FILE, "r") as f:
        device_defaults = json.load(f)
else:
    device_defaults = {}

# Load countdown state (the end timestamps) on startup
if os.path.exists(COUNTDOWN_STATE_FILE):
    with open(COUNTDOWN_STATE_FILE, "r") as f:
        devices_countdown = json.load(f)
else:
    devices_countdown = {}

def save_defaults():
    with open(DEFAULTS_FILE, "w") as f:
        json.dump(device_defaults, f)

# Function to save the current state of countdowns
def save_countdown_state():
    with open(COUNTDOWN_STATE_FILE, "w") as f:
        json.dump(devices_countdown, f)

DEFAULT_COUNTDOWN = 60 * 60 * 24 * 7  # 1 week in seconds

# ---- MQTT ----
mqtt_broker = "broker.emqx.io"
mqtt_port = 1883
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
            return

        base_topic = "/".join(topic_parts[:2])
        field_parts = topic_parts[2:]
        field = "_".join(part.lower() for part in field_parts)

        if base_topic not in latest_data:
            latest_data[base_topic] = {}
            if base_topic not in devices_countdown:
                default_duration = device_defaults.get(base_topic, DEFAULT_COUNTDOWN)
                devices_countdown[base_topic] = {
                    "end_timestamp": time.time() + default_duration,
                    "penalty_level": 0,
                    "last_penalty_check": 0 
                }
                save_countdown_state()

        latest_data[base_topic]["last_seen"] = time.time()
        payload = msg.payload.decode()

        try:
            if field != "timestamp":
                 payload = int(payload) if field == "kategori" else float(payload)
        except ValueError:
            pass

        if field not in latest_data[base_topic]:
            latest_data[base_topic][field] = deque(maxlen=MAX_HISTORY)
        
        latest_data[base_topic][field].append(payload)

        if field == "kategori":
            now_time = time.time()
            if 'timestamp' in latest_data[base_topic] and latest_data[base_topic]['timestamp']:
                try: now_time = isoparse(latest_data[base_topic]['timestamp'][-1]).timestamp()
                except (ValueError, TypeError): pass

            last_check = devices_countdown[base_topic].get("last_penalty_check", 0)
            
            if (now_time - last_check) > 86400:
                kategori_history = latest_data[base_topic].get("kategori", deque())
                CONFIRMATION_COUNT = 3

                if len(kategori_history) >= CONFIRMATION_COUNT:
                    recent_kategori = list(kategori_history)[-CONFIRMATION_COUNT:]
                    is_unacceptable = all(k == 4 for k in recent_kategori)
                    is_unsatisfactory = all(k == 3 for k in recent_kategori)
                    
                    penalty_to_apply = 0
                    latest_rms = latest_data[base_topic].get("rms", deque([0]))[-1]

                    if is_unacceptable:
                        min_rms, max_rms, min_penalty, max_penalty = 7.11, 10.0, 0.71, 0.90
                        progress = (latest_rms - min_rms) / (max_rms - min_rms)
                        penalty_to_apply = min_penalty + (progress * (max_penalty - min_penalty))
                        penalty_to_apply = max(min_penalty, min(penalty_to_apply, max_penalty))
                    elif is_unsatisfactory:
                        min_rms, max_rms, min_penalty, max_penalty = 2.81, 7.10, 0.10, 0.70
                        progress = (latest_rms - min_rms) / (max_rms - min_rms)
                        penalty_to_apply = min_penalty + (progress * (max_penalty - min_penalty))
                        penalty_to_apply = max(min_penalty, min(penalty_to_apply, max_penalty))

                    if penalty_to_apply > 0:
                        end_timestamp = devices_countdown[base_topic]["end_timestamp"]
                        remaining_time = max(0, end_timestamp - now_time)
                        time_to_reduce = remaining_time * penalty_to_apply
                        
                        devices_countdown[base_topic]["end_timestamp"] -= time_to_reduce
                        devices_countdown[base_topic]["last_penalty_check"] = now_time
                        save_countdown_state()
                        print(f"[PREDICTIVE] Daily penalty of {penalty_to_apply:.0%} applied to {base_topic} due to persistent issue.")

    except Exception as e:
        print(f"Error parsing MQTT: {e}")


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
    return """
        <h2>Go to:</h2>
        <ul>
            <li><a href='/dashboard'>/dashboard</a></li>
            <li><a href='/plot'>/plot</a></li>
            <li><a href='/cd-page'>/cd-page</a> (Countdown)</li>
            <li><a href='/end-date-page'>/end-date-page</a> (End Date)</li>
            <li><a href='/reset-page'>/reset-page</a> (Reset Button)</li>
        </ul>
    """

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

@app.route("/end-date-page")
def end_date_page():
    device_id = request.args.get("device", default=0, type=int)
    return render_template("end_date.html", device=device_id)

@app.route("/reset-page")
def reset_page():
    device_id = request.args.get("device", default=0, type=int)
    return render_template("reset_button.html", device=device_id)

@app.route("/plot")
def plot():
    device_id = request.args.get("device", default=0, type=int)
    return render_template("plot.html", device=device_id)

@app.route("/data")
def data():
    device_id = request.args.get("device", default=0, type=int)
    devices = sorted(latest_data.keys())
    if not devices: return jsonify({"error": "No devices online"})
    if not 0 <= device_id < len(devices): device_id = 0
    device_topic = devices[device_id]
    latest = {f: (v[-1] if isinstance(v, deque) else v) for f, v in latest_data[device_topic].items()}
    return jsonify({"device": device_topic, **latest})

@app.route("/devices")
def devices_list():
    now = time.time()
    devices = []
    allowed_devices = [f"Pompa{i}" for i in range(1, 6)]
    for dev, fields in latest_data.items():
        clean_name = dev.split("/")[0]
        if clean_name in allowed_devices:
            last_seen = fields.get("last_seen", 0)
            online = (now - last_seen) < 10
            devices.append({"name": clean_name, "online": online})
    return jsonify(devices)

@app.route("/get_countdown/<int:device_id>")
def get_countdown(device_id):
    devices = sorted(latest_data.keys())
    if not 0 <= device_id < len(devices): return jsonify({"error": "invalid device id"}), 404
    topic = devices[device_id]
    end_timestamp = devices_countdown.get(topic, {}).get("end_timestamp")
    if end_timestamp is None:
        default_duration = device_defaults.get(topic, DEFAULT_COUNTDOWN)
        end_timestamp = time.time() + default_duration
        devices_countdown[topic] = {"end_timestamp": end_timestamp, "penalty_level": 0, "last_penalty_check": 0}
        save_countdown_state()
    now_time = time.time()
    if 'timestamp' in latest_data.get(topic, {}) and latest_data[topic]['timestamp']:
        try:
            latest_timestamp_str = latest_data[topic]['timestamp'][-1]
            now_time = isoparse(latest_timestamp_str).timestamp()
        except (ValueError, TypeError): pass
    remaining = max(0, end_timestamp - now_time)
    return jsonify({"remaining": remaining, "pretty": format_duration(remaining)})

@app.route("/reset_countdown/<int:device_id>", methods=["POST"])
def reset_countdown(device_id):
    devices = sorted(latest_data.keys())
    if not 0 <= device_id < len(devices): return jsonify({"error": "invalid device id"}), 404
    topic = devices[device_id]
    default_duration = device_defaults.get(topic, DEFAULT_COUNTDOWN)
    now_time = time.time()
    if 'timestamp' in latest_data.get(topic, {}) and latest_data[topic]['timestamp']:
        try:
            latest_timestamp_str = latest_data[topic]['timestamp'][-1]
            now_time = isoparse(latest_timestamp_str).timestamp()
        except (ValueError, TypeError): pass
    end_timestamp = now_time + default_duration
    devices_countdown[topic] = {"end_timestamp": end_timestamp, "penalty_level": 0, "last_penalty_check": 0}
    save_countdown_state()
    return jsonify({"status": "reset", "remaining": default_duration})

@app.route("/countdown/<int:device_id>/set", methods=["POST"])
def set_countdown(device_id):
    try:
        devices = sorted(latest_data.keys())
        if not 0 <= device_id < len(devices): return jsonify({"error": "invalid device id"}), 404
        topic = devices[device_id]
        data = request.get_json(force=True)
        text = data.get("value", "")
        seconds = parse_duration(text, DEFAULT_COUNTDOWN) if text else DEFAULT_COUNTDOWN
        end_timestamp = time.time() + seconds
        devices_countdown[topic] = {"end_timestamp": end_timestamp, "penalty_level": 0, "last_penalty_check": 0}
        device_defaults[topic] = seconds
        save_defaults()
        save_countdown_state()
        return jsonify({"status": "ok", "remaining": seconds})
    except Exception as e:
        print("Error in set_countdown:", e)
        return jsonify({"error": str(e)}), 500

@app.route("/get_end_date/<int:device_id>")
def get_end_date(device_id):
    devices = sorted(latest_data.keys())
    if not 0 <= device_id < len(devices): return jsonify({"error": "invalid device id"}), 404
    topic = devices[device_id]
    end_timestamp = devices_countdown.get(topic, {}).get("end_timestamp")
    if end_timestamp is None: return jsonify({"error": "end date not set"}), 404
    # UPDATED FORMAT: YYYY MM DD
    end_date_str = datetime.datetime.fromtimestamp(end_timestamp).strftime('%Y %m %d')
    return jsonify({"end_date_str": end_date_str})

if __name__ == "__main__":
    app.run(port=5000)
