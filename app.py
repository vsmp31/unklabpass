from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
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

def init_db():
    conn = sqlite3.connect(DB_PATH)
    
    # Create users table
    conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        )
    ''')
    
    # Create vehicles table (if not exists)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS vehicles (
            plat_nomor TEXT PRIMARY KEY,
            nama_pemilik TEXT NOT NULL
        )
    ''')
    
    # Create gate_logs table (if not exists)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS gate_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plat_nomor TEXT NOT NULL,
            entry_time DATETIME NOT NULL,
            FOREIGN KEY (plat_nomor) REFERENCES vehicles(plat_nomor)
        )
    ''')
    
    # ─── CREATE INDEXES untuk performa query yang lebih cepat ───
    # Index untuk gate_logs.entry_time (untuk ORDER BY entry_time DESC)
    conn.execute('''
        CREATE INDEX IF NOT EXISTS idx_gate_logs_entry_time 
        ON gate_logs(entry_time DESC)
    ''')
    
    # Index untuk gate_logs.plat_nomor (untuk JOIN dengan vehicles)
    conn.execute('''
        CREATE INDEX IF NOT EXISTS idx_gate_logs_plat_nomor 
        ON gate_logs(plat_nomor)
    ''')
    
    # Index untuk users.username (untuk login query)
    conn.execute('''
        CREATE INDEX IF NOT EXISTS idx_users_username 
        ON users(username)
    ''')
    
    # Check if admin exists
    admin = conn.execute("SELECT * FROM users WHERE username = 'admin'").fetchone()
    if not admin:
        default_hash = generate_password_hash("admin123")
        conn.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", ("admin", default_hash))
    
    conn.commit()
    conn.close()
    logging.info("[DB] Database initialized with indexes for optimal performance")

# Run it on startup
init_db()

# Verify indexes on startup
def verify_indexes():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT COUNT(*) FROM sqlite_master 
        WHERE type = 'index' 
        AND name LIKE 'idx_%'
    """)
    count = cursor.fetchone()[0]
    conn.close()
    
    if count >= 3:
        logging.info(f"[DB] ✅ {count} custom indexes verified")
    else:
        logging.warning(f"[DB] ⚠️  Only {count} indexes found. Expected at least 3.")

verify_indexes()

# In-Memory Cache for fast O(1) lookups
CACHE_VEHICLES = []

def load_vehicles():
    global CACHE_VEHICLES
    if not CACHE_VEHICLES:
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT plat_nomor, nama_pemilik FROM vehicles").fetchall()
            conn.close()
            CACHE_VEHICLES = [{"plate": r["plat_nomor"], "name": r["nama_pemilik"]} for r in rows]
            logging.info(f"[CACHE] Database loaded into RAM. Vehicles: {len(CACHE_VEHICLES)}")
        except Exception as e:
            logging.error(f"[CACHE] Failed to load DB: {e}")
            return []
    return CACHE_VEHICLES


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

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        conn.close()
        
        if user and check_password_hash(user["password_hash"], password):
            session["logged_in"] = True
            session["username"] = username
            return redirect(url_for("dashboard"))
        else:
            return render_template("login.html", error="Username atau Password salah!")
            
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))

# ─── API ──────────────────────────────────────────────────────────────────────

@app.route("/analyze", methods=["POST"])
def analyze():
    try:
        data      = request.get_json(force=True)
        images    = data.get("image", "")
        
        if isinstance(images, str):
            images = [images]
            
        if not images or not images[0]:
            return jsonify({"success": False, "error": "No image data received"}), 400

        vehicles  = load_vehicles()
        scan_time = time.strftime("%Y-%m-%d %H:%M:%S")

        final_result = None
        for b64_img in images:
            if not b64_img:
                continue
            res = analyze_frame(b64_img, vehicles)
            if res.get("found") and res.get("plate"):
                final_result = res
                break
            if final_result is None:
                final_result = res
                
        result = final_result

        if result["found"] and result["plate"]:
            plate_to_log = result["plate"]
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            
            # Cooldown check: Hanya tulis ke log jika plat nomornya berbeda dari baris log terakhir
            cur.execute("""
                SELECT plat_nomor FROM gate_logs 
                ORDER BY entry_time DESC LIMIT 1
            """)
            last_logged = cur.fetchone()
            
            should_log = True
            if last_logged and last_logged[0] == plate_to_log:
                should_log = False
                    
            if should_log:
                cur.execute("""
                    INSERT INTO gate_logs (plat_nomor, entry_time) 
                    VALUES (?, ?)
                """, (plate_to_log, scan_time))
                conn.commit()
                logging.info(f"[DB LOG] Plat {plate_to_log} tercatat pada {scan_time}.")
            
            conn.close()

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


# ─── Dashboard & CRUD Endpoints ───────────────────────────────────────────────

@app.route("/dashboard")
def dashboard():
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    return render_template("dashboard.html", page="dashboard")

@app.route("/api/vehicles", methods=["GET"])
def api_get_vehicles():
    return jsonify(load_vehicles())

@app.route("/api/vehicles", methods=["POST"])
def api_add_vehicle():
    if not session.get("logged_in"):
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    global CACHE_VEHICLES
    data = request.json
    plate = data.get("plate", "").replace(" ", "").upper()
    name = data.get("name", "").strip()
    if not plate or not name:
        return jsonify({"success": False, "error": "Plate and Name required"}), 400
        
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("INSERT INTO vehicles (plat_nomor, nama_pemilik) VALUES (?, ?)", (plate, name))
        conn.commit()
        conn.close()
        CACHE_VEHICLES = [] # Invalidate cache
        return jsonify({"success": True})
    except sqlite3.IntegrityError:
        return jsonify({"success": False, "error": "Plate already registered"}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/vehicles", methods=["PUT"])
def api_update_vehicle():
    if not session.get("logged_in"):
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    global CACHE_VEHICLES
    data = request.json
    old_plate = data.get("old_plate", "").replace(" ", "").upper()
    new_plate = data.get("new_plate", "").replace(" ", "").upper()
    name = data.get("name", "").strip()
    
    if not old_plate or not new_plate or not name:
        return jsonify({"success": False, "error": "Incomplete data"}), 400
        
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("UPDATE vehicles SET plat_nomor = ?, nama_pemilik = ? WHERE plat_nomor = ?", (new_plate, name, old_plate))
        conn.commit()
        conn.close()
        CACHE_VEHICLES = [] # Invalidate cache
        return jsonify({"success": True})
    except sqlite3.IntegrityError:
        return jsonify({"success": False, "error": "New plate already exists"}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/vehicles/<plate>", methods=["DELETE"])
def api_delete_vehicle(plate):
    if not session.get("logged_in"):
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    global CACHE_VEHICLES
    plate = plate.replace(" ", "").upper()
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("DELETE FROM vehicles WHERE plat_nomor = ?", (plate,))
        conn.commit()
        conn.close()
        CACHE_VEHICLES = [] # Invalidate cache
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/logs", methods=["GET"])
def api_get_logs():
    try:
        # Get pagination parameters
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        
        # Validate parameters
        if page < 1:
            page = 1
        if per_page < 1 or per_page > 100:
            per_page = 20
        
        offset = (page - 1) * per_page
        
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        
        # Get total count
        count_query = "SELECT COUNT(*) as total FROM gate_logs"
        total = conn.execute(count_query).fetchone()['total']
        
        # Get paginated logs
        query = """
            SELECT l.plat_nomor, l.entry_time, v.nama_pemilik
            FROM gate_logs l
            LEFT JOIN vehicles v ON l.plat_nomor = v.plat_nomor
            ORDER BY l.entry_time DESC
            LIMIT ? OFFSET ?
        """
        rows = conn.execute(query, (per_page, offset)).fetchall()
        conn.close()
        
        logs = []
        for r in rows:
            logs.append({
                "plate": r["plat_nomor"],
                "time": r["entry_time"],
                "name": r["nama_pemilik"],
                "registered": bool(r["nama_pemilik"])
            })
        
        return jsonify({
            "logs": logs,
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "total_pages": (total + per_page - 1) // per_page
            }
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


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
