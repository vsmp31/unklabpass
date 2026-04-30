from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
import time
import os
import glob
import logging

from plate_detector import analyze_frame

# Setup logging untuk monitoring sistem
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")

app = Flask(__name__)
app.secret_key = "scanvec-unklabpass-2026"

# ═══ Konfigurasi Auto-reload & Cache ═══════════════════════════════════════
app.config["TEMPLATES_AUTO_RELOAD"]    = True
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0

@app.after_request
def no_cache(response):
    """Disable cache untuk development - selalu load file terbaru"""
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"]        = "no-cache"
    response.headers["Expires"]       = "0"
    return response

# Path ke database SQLite
DB_PATH = os.path.join(os.path.dirname(__file__), "data", "vehicles.db")

def init_db():
    """
    Inisialisasi database: buat tabel dan index jika belum ada
    Dipanggil saat aplikasi pertama kali dijalankan
    """
    conn = sqlite3.connect(DB_PATH)
    
    # Buat tabel users untuk login
    conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        )
    ''')
    
    # Buat tabel vehicles untuk data kendaraan terdaftar
    conn.execute('''
        CREATE TABLE IF NOT EXISTS vehicles (
            plat_nomor TEXT PRIMARY KEY,
            nama_pemilik TEXT NOT NULL
        )
    ''')
    
    # Buat tabel gate_logs untuk histori keluar-masuk
    conn.execute('''
        CREATE TABLE IF NOT EXISTS gate_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plat_nomor TEXT NOT NULL,
            entry_time DATETIME NOT NULL,
            FOREIGN KEY (plat_nomor) REFERENCES vehicles(plat_nomor)
        )
    ''')
    
    # ═══ BUAT INDEX untuk performa query lebih cepat ═══
    # Index untuk sorting logs berdasarkan waktu (DESC)
    conn.execute('''
        CREATE INDEX IF NOT EXISTS idx_gate_logs_entry_time 
        ON gate_logs(entry_time DESC)
    ''')
    
    # Index untuk JOIN antara gate_logs dan vehicles
    conn.execute('''
        CREATE INDEX IF NOT EXISTS idx_gate_logs_plat_nomor 
        ON gate_logs(plat_nomor)
    ''')
    
    # Index untuk query login (cari username)
    conn.execute('''
        CREATE INDEX IF NOT EXISTS idx_users_username 
        ON users(username)
    ''')
    
    # Cek apakah user admin sudah ada, jika belum buat default
    admin = conn.execute("SELECT * FROM users WHERE username = 'admin'").fetchone()
    if not admin:
        default_hash = generate_password_hash("admin123")
        conn.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", ("admin", default_hash))
    
    conn.commit()
    conn.close()
    logging.info("[DB] Database berhasil diinisialisasi dengan indexes untuk performa optimal")

# Jalankan inisialisasi database saat startup
init_db()

# Verifikasi indexes saat startup
def verify_indexes():
    """Cek apakah semua custom indexes sudah terbuat dengan benar"""
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
        logging.info(f"[DB] ✅ {count} custom indexes berhasil diverifikasi")
    else:
        logging.warning(f"[DB] ⚠️  Hanya {count} indexes ditemukan. Seharusnya minimal 3.")

verify_indexes()

# ═══ In-Memory Cache untuk Lookup Cepat O(1) ═══════════════════════════════
CACHE_VEHICLES = []

def load_vehicles():
    """
    Load data vehicles dari database ke RAM (cache)
    Cache digunakan untuk lookup cepat saat analyze frame
    Cache di-invalidate setiap kali ada perubahan data (INSERT/UPDATE/DELETE)
    """
    global CACHE_VEHICLES
    if not CACHE_VEHICLES:
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT plat_nomor, nama_pemilik FROM vehicles").fetchall()
            conn.close()
            CACHE_VEHICLES = [{"plate": r["plat_nomor"], "name": r["nama_pemilik"]} for r in rows]
            logging.info(f"[CACHE] Database berhasil dimuat ke RAM. Total kendaraan: {len(CACHE_VEHICLES)}")
        except Exception as e:
            logging.error(f"[CACHE] Gagal load database: {e}")
            return []
    return CACHE_VEHICLES

# ═══════════════════════════════════════════════════════════════════════════
# HALAMAN WEB
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/")
def home():
    """Halaman utama - scan kendaraan dengan kamera"""
    detected  = session.get("detected")
    scan_time = session.get("scan_time", "—")
    akurasi   = session.get("akurasi", "—")
    return render_template("home.html", page="home",
                           detected=detected,
                           scan_time=scan_time,
                           akurasi=akurasi)


@app.route("/about")
def about():
    """Halaman tentang aplikasi"""
    return render_template("about.html", page="about")

@app.route("/login", methods=["GET", "POST"])
def login():
    """Halaman login untuk akses dashboard admin"""
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        
        # Cari user di database
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        conn.close()
        
        # Verifikasi password
        if user and check_password_hash(user["password_hash"], password):
            session["logged_in"] = True
            session["username"] = username
            return redirect(url_for("dashboard"))
        else:
            return render_template("login.html", error="Username atau Password salah!")
            
    return render_template("login.html")

@app.route("/logout")
def logout():
    """Logout - hapus session dan redirect ke home"""
    session.clear()
    return redirect(url_for("home"))

# ═══════════════════════════════════════════════════════════════════════════
# API ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/analyze", methods=["POST"])
def analyze():
    """
    API untuk analyze frame dari kamera
    Menerima vector 5 images (anti-blur), detect plat dengan YOLOv8 + EasyOCR
    Jika plat terdaftar, simpan ke gate_logs
    """
    try:
        data      = request.get_json(force=True)
        images    = data.get("image", "")
        
        # Convert single image ke array
        if isinstance(images, str):
            images = [images]
            
        if not images or not images[0]:
            return jsonify({"success": False, "error": "No image data received"}), 400

        # Load vehicles dari cache
        vehicles  = load_vehicles()
        scan_time = time.strftime("%Y-%m-%d %H:%M:%S")

        # Analyze setiap frame dalam vector, ambil hasil terbaik
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

        # Jika plat terdeteksi, simpan ke database logs
        if result["found"] and result["plate"]:
            plate_to_log = result["plate"]
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            
            # Cooldown check: Hanya tulis ke log jika plat berbeda dari log terakhir
            cur.execute("""
                SELECT plat_nomor FROM gate_logs 
                ORDER BY entry_time DESC LIMIT 1
            """)
            last_logged = cur.fetchone()
            
            should_log = True
            if last_logged and last_logged[0] == plate_to_log:
                should_log = False  # Skip duplicate
                    
            if should_log:
                # INSERT ke gate_logs
                cur.execute("""
                    INSERT INTO gate_logs (plat_nomor, entry_time) 
                    VALUES (?, ?)
                """, (plate_to_log, scan_time))
                conn.commit()
                logging.info(f"[DB LOG] Plat {plate_to_log} tercatat pada {scan_time}.")
            
            conn.close()

        # Prepare response
        base = {
            "success":    True,
            "found":      result["found"],
            "registered": result["registered"],
            "plate":      result["plate"],
            "scan_time":  scan_time,
            "boxes":      result["boxes"],
            "frame_size": result["frame_size"],
        }

        # Jika kendaraan terdaftar, tambahkan info pemilik
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
    """Clear session data"""
    session.clear()
    return jsonify({"success": True})


# ═══════════════════════════════════════════════════════════════════════════
# DASHBOARD & CRUD ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/dashboard")
def dashboard():
    """Halaman dashboard admin - hanya bisa diakses setelah login"""
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    return render_template("dashboard.html", page="dashboard")

@app.route("/api/vehicles", methods=["GET"])
def api_get_vehicles():
    """
    GET /api/vehicles - Ambil semua data kendaraan
    Support search query: ?search=DB123
    """
    search = request.args.get('search', '').strip()
    
    if search:
        # Search by plat nomor atau nama pemilik
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        query = """
            SELECT plat_nomor, nama_pemilik 
            FROM vehicles 
            WHERE plat_nomor LIKE ? OR nama_pemilik LIKE ?
            ORDER BY plat_nomor
        """
        search_pattern = f"%{search}%"
        rows = conn.execute(query, (search_pattern, search_pattern)).fetchall()
        conn.close()
        
        vehicles = [{"plate": r["plat_nomor"], "name": r["nama_pemilik"]} for r in rows]
        return jsonify(vehicles)
    else:
        # Return dari cache
        return jsonify(load_vehicles())

@app.route("/api/vehicles", methods=["POST"])
def api_add_vehicle():
    """
    POST /api/vehicles - Tambah kendaraan baru
    Body: {"plate": "DB123", "name": "John Doe"}
    """
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
        CACHE_VEHICLES = []  # Invalidate cache
        return jsonify({"success": True})
    except sqlite3.IntegrityError:
        return jsonify({"success": False, "error": "Plate already registered"}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/vehicles", methods=["PUT"])
def api_update_vehicle():
    """
    PUT /api/vehicles - Update data kendaraan
    Body: {"old_plate": "DB123", "new_plate": "DB123A", "name": "John Doe"}
    """
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
        CACHE_VEHICLES = []  # Invalidate cache
        return jsonify({"success": True})
    except sqlite3.IntegrityError:
        return jsonify({"success": False, "error": "New plate already exists"}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/vehicles/<plate>", methods=["DELETE"])
def api_delete_vehicle(plate):
    """
    DELETE /api/vehicles/:plate - Hapus kendaraan
    """
    if not session.get("logged_in"):
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    
    global CACHE_VEHICLES
    plate = plate.replace(" ", "").upper()
    
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("DELETE FROM vehicles WHERE plat_nomor = ?", (plate,))
        conn.commit()
        conn.close()
        CACHE_VEHICLES = []  # Invalidate cache
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/logs", methods=["GET"])
def api_get_logs():
    """
    GET /api/logs - Ambil histori gate logs dengan pagination dan filtering
    Query params:
    - page: nomor halaman (default: 1)
    - per_page: jumlah data per halaman (default: 20, max: 100)
    - search: cari berdasarkan plat nomor atau nama pemilik
    - date_from: filter dari tanggal (format: YYYY-MM-DD)
    - date_to: filter sampai tanggal (format: YYYY-MM-DD)
    - time_from: filter dari jam (format: HH:MM)
    - time_to: filter sampai jam (format: HH:MM)
    - specific_date: filter tanggal spesifik (format: YYYY-MM-DD)
    """
    try:
        # Ambil parameter pagination dan search
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        search = request.args.get('search', '').strip()
        
        # Ambil parameter filtering
        date_from = request.args.get('date_from', '').strip()
        date_to = request.args.get('date_to', '').strip()
        time_from = request.args.get('time_from', '').strip()
        time_to = request.args.get('time_to', '').strip()
        specific_date = request.args.get('specific_date', '').strip()
        
        # Validasi parameter
        if page < 1:
            page = 1
        if per_page < 1 or per_page > 100:
            per_page = 20
        
        offset = (page - 1) * per_page
        
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        
        # Build WHERE clause untuk filtering
        where_conditions = []
        params = []
        
        # Filter search (plat nomor atau nama)
        if search:
            where_conditions.append("(l.plat_nomor LIKE ? OR v.nama_pemilik LIKE ?)")
            search_pattern = f"%{search}%"
            params.extend([search_pattern, search_pattern])
        
        # Filter specific date (prioritas tertinggi)
        if specific_date:
            where_conditions.append("DATE(l.entry_time) = ?")
            params.append(specific_date)
        else:
            # Filter date range
            if date_from:
                where_conditions.append("DATE(l.entry_time) >= ?")
                params.append(date_from)
            if date_to:
                where_conditions.append("DATE(l.entry_time) <= ?")
                params.append(date_to)
        
        # Filter time range (jam:menit)
        if time_from:
            where_conditions.append("TIME(l.entry_time) >= ?")
            params.append(time_from + ":00")
        if time_to:
            where_conditions.append("TIME(l.entry_time) <= ?")
            params.append(time_to + ":59")
        
        # Gabungkan WHERE conditions
        where_clause = ""
        if where_conditions:
            where_clause = "WHERE " + " AND ".join(where_conditions)
        
        # Query count dengan filter
        count_query = f"""
            SELECT COUNT(*) as total 
            FROM gate_logs l
            LEFT JOIN vehicles v ON l.plat_nomor = v.plat_nomor
            {where_clause}
        """
        total = conn.execute(count_query, params).fetchone()['total']
        
        # Query logs dengan filter dan pagination
        query = f"""
            SELECT l.plat_nomor, l.entry_time, v.nama_pemilik
            FROM gate_logs l
            LEFT JOIN vehicles v ON l.plat_nomor = v.plat_nomor
            {where_clause}
            ORDER BY l.entry_time DESC
            LIMIT ? OFFSET ?
        """
        rows = conn.execute(query, params + [per_page, offset]).fetchall()
        
        conn.close()
        
        # Convert ke JSON format
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
                "total_pages": (total + per_page - 1) // per_page if total > 0 else 1
            }
        })
    except Exception as e:
        logging.exception("Error in /api/logs")
        return jsonify({"error": str(e)}), 500


# ═══════════════════════════════════════════════════════════════════════════
# RUN APPLICATION
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # Collect semua templates & static files agar Flask reloader watch perubahan
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
