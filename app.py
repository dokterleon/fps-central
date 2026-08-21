from flask import Flask, render_template, jsonify, request, Response
from flask_cors import CORS
import json, os, time, functools
from datetime import datetime

app = Flask(__name__)
CORS(app, resources={r"/api/ping": {"origins": "*"}})

DATA_FILE  = "data/clients.json"
API_KEY    = os.environ.get("FPS_API_KEY",    "flitshokje-secret-2026")
DASH_USER  = os.environ.get("FPS_DASH_USER",  "fps")
DASH_PASS  = os.environ.get("FPS_DASH_PASS",  "flitshokje2026")

os.makedirs("data", exist_ok=True)

# ── basic auth ────────────────────────────────────────────────────────────────

def check_auth(username, password):
    return username == DASH_USER and password == DASH_PASS

def require_auth(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return Response(
                "FPS Centrale beheer — inloggen vereist",
                401,
                {"WWW-Authenticate": 'Basic realm="FPS Central"'}
            )
        return f(*args, **kwargs)
    return decorated

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

# ── ping endpoint ─────────────────────────────────────────────────────────────

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
        "client_id":  client_id,
        "name":       d.get("name", client_id),
        "location":   d.get("location", "—"),
        "ip":         d.get("ip", "—"),
        "version":    d.get("version", "—"),
        "printers":   d.get("printers", []),
        "temp":       d.get("temp"),
        "uptime":     d.get("uptime", "—"),
        "disk_pct":   d.get("disk_pct", 0),
        "airprint":   d.get("airprint", False),
        "errors":     d.get("errors", []),
        "last_seen":  datetime.now().strftime("%d-%m %H:%M"),
        "last_ts":    time.time(),
    }
    save(clients)
    return jsonify({"ok": True})

# ── publieke status pagina (geen auth) ───────────────────────────────────────

@app.route("/status/<client_id>")
def public_status(client_id):
    return render_template("status.html")

@app.route("/api/status/<client_id>")
def api_public_status(client_id):
    clients = load()
    c = clients.get(client_id)
    if not c:
        return jsonify({"error": "not found"}), 404
    c["online"] = (time.time() - c.get("last_ts", 0)) < 360
    return jsonify(c)

# ── beheerder dashboard (wel auth) ───────────────────────────────────────────

@app.route("/")
@require_auth
def index():
    return render_template("index.html")

@app.route("/api/clients")
@require_auth
def api_clients():
    clients = load()
    now = time.time()
    result = []
    for c in clients.values():
        c["online"] = (now - c.get("last_ts", 0)) < 360
        result.append(c)
    result.sort(key=lambda x: x.get("last_ts", 0), reverse=True)
    return jsonify(result)


# ── licentie validatie ────────────────────────────────────────────────────────
@app.route("/api/validate", methods=["POST"])
def validate():
    key = request.headers.get("X-API-Key", "")
    if key != API_KEY:
        return jsonify({"valid": False, "reason": "unauthorized"}), 401
    d = request.json or {}
    client_id = d.get("client_id")
    hardware_id = d.get("hardware_id")
    if not client_id or not hardware_id:
        return jsonify({"valid": False, "reason": "missing fields"}), 400
    clients = load()
    c = clients.get(client_id)
    # Onbekende client_id
    if not c:
        return jsonify({"valid": False, "reason": "unknown_client"}), 403
    # Geblokkeerd
    if c.get("blocked", False):
        return jsonify({"valid": False, "reason": "blocked"}), 403
    # Hardware check — clone detectie
    registered_hw = c.get("hardware_id")
    if registered_hw and registered_hw != hardware_id:
        return jsonify({"valid": False, "reason": "hardware_mismatch"}), 403
    # Eerste keer — hardware_id opslaan
    if not registered_hw:
        c["hardware_id"] = hardware_id
    # Licentie verlopen
    import time as _time
    expires = c.get("expires_at")
    if expires and _time.time() > expires:
        return jsonify({"valid": False, "reason": "expired"}), 403
    # Alles OK
    c["hardware_id"] = hardware_id
    c["last_validated"] = __import__('datetime').datetime.now().strftime("%d-%m %H:%M")
    c["licensed"] = c.get("licensed", True)
    clients[client_id] = c
    save(clients)
    return jsonify({
        "valid": True,
        "demo": c.get("demo", False),
        "licensed": c.get("licensed", True),
        "client_id": client_id
    })

# ── unit beheer (blokkeren/activeren) ────────────────────────────────────────
@app.route("/api/unit/<client_id>/block", methods=["POST"])
@require_auth
def block_unit(client_id):
    clients = load()
    if client_id not in clients:
        return jsonify({"error": "not found"}), 404
    clients[client_id]["blocked"] = True
    save(clients)
    return jsonify({"ok": True, "blocked": True})

@app.route("/api/unit/<client_id>/unblock", methods=["POST"])
@require_auth
def unblock_unit(client_id):
    clients = load()
    if client_id not in clients:
        return jsonify({"error": "not found"}), 404
    clients[client_id]["blocked"] = False
    save(clients)
    return jsonify({"ok": True, "blocked": False})

@app.route("/api/unit/<client_id>/reset-hardware", methods=["POST"])
@require_auth
def reset_hardware(client_id):
    clients = load()
    if client_id not in clients:
        return jsonify({"error": "not found"}), 404
    clients[client_id]["hardware_id"] = None
    save(clients)
    return jsonify({"ok": True, "message": "hardware_id gewist"})

@app.route("/api/unit/<client_id>/demo", methods=["POST"])
@require_auth
def set_demo(client_id):
    clients = load()
    if client_id not in clients:
        return jsonify({"error": "not found"}), 404
    clients[client_id]["demo"] = request.json.get("demo", True)
    save(clients)
    return jsonify({"ok": True})


@app.route("/api/unit/<client_id>/delete", methods=["POST"])
@require_auth
def delete_unit(client_id):
    clients = load()
    if client_id not in clients:
        return jsonify({"error": "not found"}), 404
    del clients[client_id]
    save(clients)
    return jsonify({"ok": True, "deleted": client_id})


@app.route("/api/unit/<client_id>/delete", methods=["POST"])
@require_auth
def delete_unit(client_id):
    clients = load()
    if client_id not in clients:
        return jsonify({"error": "not found"}), 404
    del clients[client_id]
    save(clients)
    return jsonify({"ok": True, "deleted": client_id})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
