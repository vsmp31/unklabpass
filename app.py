from flask import Flask, render_template, request, jsonify, session
import sqlite3
import time
import os
import glob
import logging

from plate_detector import analyze_frame

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")

app = Flask(__name__)
app.secret_key = "scanvec-unklabpass-2026"

# ─── Auto-reload & cache config ───────────────────────────────────────────────
app.config["TEMPLATES_AUTO_RELOAD"]    = True
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0

@app.after_request
def no_cache(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"]        = "no-cache"
    response.headers["Expires"]       = "0"
    return response

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "vehicles.db")


def load_vehicles():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT plat_nomor, nama_pemilik FROM vehicles").fetchall()
    conn.close()
    return [{"plate": r["plat_nomor"], "name": r["nama_pemilik"]} for r in rows]


# ─── Pages ────────────────────────────────────────────────────────────────────

@app.route("/")
def home():
    detected  = session.get("detected")
    scan_time = session.get("scan_time", "—")
    akurasi   = session.get("akurasi", "—")
    return render_template("home.html", page="home",
                           detected=detected,
                           scan_time=scan_time,
                           akurasi=akurasi)


@app.route("/about")
def about():
    return render_template("about.html", page="about")


# ─── API ──────────────────────────────────────────────────────────────────────

@app.route("/analyze", methods=["POST"])
def analyze():
    try:
        data      = request.get_json(force=True)
        b64_image = data.get("image", "")
        if not b64_image:
            return jsonify({"success": False, "error": "No image data received"}), 400

        vehicles  = load_vehicles()
        scan_time = time.strftime("%Y-%m-%d %H:%M:%S")

        result = analyze_frame(b64_image, vehicles)

        base = {
            "success":    True,
            "found":      result["found"],
            "registered": result["registered"],
            "plate":      result["plate"],
            "scan_time":  scan_time,
            "boxes":      result["boxes"],
            "frame_size": result["frame_size"],
        }

        if result["registered"] and result["lecturer"]:
            vehicle = result["lecturer"]
            session["detected"]  = vehicle
            session["scan_time"] = scan_time
            base.update({
                "name": vehicle.get("name", "—"),
            })

        return jsonify(base)

    except Exception as e:
        logging.exception("Error in /analyze")
        return jsonify({"success": False, "error": str(e)}), 500



@app.route("/clear", methods=["POST"])
def clear():
    session.clear()
    return jsonify({"success": True})


# ─── Run ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Collect all templates & static files so Flask reloader watches them too
    BASE = os.path.dirname(__file__)
    extra_files = (
        glob.glob(os.path.join(BASE, "templates", "**", "*"), recursive=True) +
        glob.glob(os.path.join(BASE, "static",    "**", "*"), recursive=True)
    )
    app.run(
        debug=True,
        port=5000,
        host="0.0.0.0",
        use_reloader=True,
        extra_files=extra_files,
    )
