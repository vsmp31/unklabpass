from flask import Flask, render_template, request, jsonify, session
import json
import random
import time
import os

app = Flask(__name__)
app.secret_key = "scanvec-unklabpass-2026"

DATA_PATH = os.path.join(os.path.dirname(__file__), "data", "lecturers.json")


def load_lecturers():
    with open(DATA_PATH, encoding="utf-8") as f:
        return json.load(f)


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
        lecturers = load_lecturers()
        detected  = random.choice(lecturers)
        scan_time = time.strftime("%Y-%m-%d %H:%M:%S")
        akurasi   = random.randint(88, 99)

        session["detected"]  = detected
        session["scan_time"] = scan_time
        session["akurasi"]   = f"{akurasi}%"

        return jsonify({
            "success":    True,
            "plate":      detected["plate"],
            "name":       detected["name"],
            "department": detected.get("department", "—"),
            "scan_time":  scan_time,
            "accuracy":   f"{akurasi}%",
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/clear", methods=["POST"])
def clear():
    session.clear()
    return jsonify({"success": True})


# ─── Run ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=True, port=5000, host="0.0.0.0")
