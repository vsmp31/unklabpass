"""
init_db.py
──────────
Generate SQLite database with 100 random Indonesian vehicle plates and owner names.
Table: vehicles (plat_nomor TEXT PRIMARY KEY, nama_pemilik TEXT)
"""

import sqlite3
import random
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "vehicles.db")

KODE_WILAYAH = [
    "A", "B", "D", "E", "F", "G", "H", "K", "L", "M", "N",
    "S", "W", "AB", "AD", "AG", "BE", "BG", "BH", "BK", "BL",
    "BM", "BN", "BP", "DA", "DB", "DC", "DD", "DE", "DG", "DH",
    "DK", "DL", "DM", "DN", "DR", "DS", "DT", "DW", "EA", "EB",
    "ED", "KB", "KH", "KT", "KU", "PA", "PB",
]

NAMA_DEPAN = [
    "Andi", "Budi", "Citra", "Dewi", "Eka", "Fajar", "Gita", "Hendra",
    "Indra", "Joko", "Kevin", "Lina", "Maria", "Nico", "Oscar", "Putri",
    "Randi", "Sari", "Tono", "Umar", "Vina", "Wati", "Yanto", "Zahra",
    "Agus", "Bayu", "Dian", "Fitri", "Galih", "Hani", "Irfan", "Jasmine",
    "Kurnia", "Lestari", "Mulyadi", "Nanda", "Okta", "Prasetyo", "Rina",
    "Surya", "Teguh", "Utami", "Wahyu", "Yuni", "Arief", "Bambang",
    "Chandra", "Doni", "Endah", "Farhan",
]

NAMA_BELAKANG = [
    "Susanto", "Wijaya", "Pratama", "Saputra", "Hidayat", "Nugroho",
    "Santoso", "Permana", "Kusuma", "Hartono", "Suryadi", "Putra",
    "Gunawan", "Siregar", "Nasution", "Panjaitan", "Simanjuntak",
    "Hutapea", "Sitorus", "Manalu", "Tampubolon", "Siahaan",
    "Lumbantobing", "Pardede", "Napitupulu", "Aritonang", "Situmorang",
    "Simbolon", "Turnip", "Samosir", "Hutabarat", "Simatupang",
    "Rajagukguk", "Pakpahan", "Silalahi", "Sinaga", "Purba",
    "Damanik", "Saragih", "Nainggolan",
]

HURUF = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def generate_plate():
    kode = "DB"  # Sulawesi Utara (Manado) - lokasi Universitas Klabat
    angka = random.randint(1, 9999)
    akhir_len = random.choice([1, 2, 3])
    akhir = "".join(random.choices(HURUF, k=akhir_len))
    return f"{kode} {angka} {akhir}"


def generate_name():
    return f"{random.choice(NAMA_DEPAN)} {random.choice(NAMA_BELAKANG)}"


def main():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE vehicles (
            plat_nomor  TEXT PRIMARY KEY,
            nama_pemilik TEXT NOT NULL
        )
    """)

    plates_seen = set()
    rows = []
    while len(rows) < 100:
        plate = generate_plate()
        if plate in plates_seen:
            continue
        plates_seen.add(plate)
        rows.append((plate, generate_name()))

    cur.executemany("INSERT INTO vehicles VALUES (?, ?)", rows)
    conn.commit()

    cur.execute("SELECT COUNT(*) FROM vehicles")
    count = cur.fetchone()[0]
    print(f"Database created: {DB_PATH}")
    print(f"Total records: {count}")

    cur.execute("SELECT * FROM vehicles LIMIT 5")
    print("\nSample data:")
    for row in cur.fetchall():
        print(f"  {row[0]:>15}  |  {row[1]}")

    conn.close()


if __name__ == "__main__":
    main()
