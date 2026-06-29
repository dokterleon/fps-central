from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
import json, os, time
from datetime import datetime

app = Flask(__name__)
CORS(app)

DATA_FILE = "data/clients.json"
API_KEY   = os.environ.get("FPS_API_KEY", "flitshokje-secret-2026")

os.makedirs("data", exist_ok=True)

# ── data helpers ──────────────────────────────────────────────────────────────

def load():
    try:
        with open(DATA_FILE) as f:
            return json.load(f)
    except Exception:
        return {}

def save(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

# ── ping endpoint (Pi's sturen hierheen) ─────────────────────────────────────

@app.route("/api/ping", methods=["POST"])
def ping():
    key = request.headers.get("X-API-Key", "")
    if key != API_KEY:
        return jsonify({"error": "unauthorized"}), 401

    d = request.json or {}
    client_id = d.get("client_id")
    if not client_id:
        return jsonify({"error": "no client_id"}), 400

    clients = load()
    clients[client_id] = {
        "client_id":   client_id,
        "name":        d.get("name", client_id),
        "location":    d.get("location", "—"),
        "ip":          d.get("ip", "—"),
        "version":     d.get("version", "—"),
        "printers":    d.get("printers", []),
        "temp":        d.get("temp"),
        "uptime":      d.get("uptime", "—"),
        "disk_pct":    d.get("disk_pct", 0),
        "airprint":    d.get("airprint", False),
        "errors":      d.get("errors", []),
        "last_seen":   datetime.now().strftime("%d-%m %H:%M"),
        "last_ts":     time.time(),
    }
    save(clients)
    return jsonify({"ok": True})

# ── dashboard ─────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/clients")
def api_clients():
    clients = load()
    now = time.time()
    result = []
    for c in clients.values():
        c["online"] = (now - c.get("last_ts", 0)) < 360  # 6 min timeout
        result.append(c)
    result.sort(key=lambda x: x.get("last_ts", 0), reverse=True)
    return jsonify(result)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
