# 🗑️ Cara Delete Logs dari Database

## 📋 3 Cara Delete Logs

### 1. ⚡ **Menggunakan Dashboard (TERMUDAH)**

#### A. Clear All Logs
1. Login ke dashboard: `http://localhost:5000/login`
2. Klik tab **"Dashboard"**
3. Di panel **Logs** (kanan), klik icon **🗑️ Trash** (merah)
4. Konfirmasi: Klik **"Hapus Semua"**
5. ✅ Semua logs terhapus!

**Keuntungan:**
- ✅ Paling mudah (1 klik)
- ✅ Ada konfirmasi
- ✅ Tidak perlu install software tambahan

---

### 2. 💾 **Menggunakan DB Browser for SQLite**

#### A. Install DB Browser
Download dari: https://sqlitebrowser.org/dl/

#### B. Delete Semua Logs
1. Buka **DB Browser for SQLite**
2. File → **Open Database** → Pilih `data/vehicles.db`
3. Klik tab **"Execute SQL"**
4. Ketik query:
   ```sql
   DELETE FROM gate_logs;
   ```
5. Klik **Execute** (icon play ▶️)
6. Klik **Write Changes** (icon save 💾)
7. ✅ Semua logs terhapus!

#### C. Delete Logs Berdasarkan Tanggal
```sql
-- Delete logs sebelum tanggal tertentu
DELETE FROM gate_logs WHERE entry_time < '2026-05-01';

-- Delete logs hari ini
DELETE FROM gate_logs WHERE DATE(entry_time) = DATE('now');

-- Delete logs 7 hari terakhir
DELETE FROM gate_logs WHERE entry_time >= DATE('now', '-7 days');

-- Delete logs bulan ini
DELETE FROM gate_logs WHERE strftime('%Y-%m', entry_time) = strftime('%Y-%m', 'now');

-- Delete logs tahun ini
DELETE FROM gate_logs WHERE strftime('%Y', entry_time) = strftime('%Y', 'now');
```

#### D. Delete Logs Berdasarkan Plat
```sql
-- Delete logs untuk plat tertentu
DELETE FROM gate_logs WHERE plat_nomor = 'DB1282WD';

-- Delete logs untuk plat yang tidak terdaftar
DELETE FROM gate_logs 
WHERE plat_nomor NOT IN (SELECT plat_nomor FROM vehicles);

-- Delete logs untuk plat yang terdaftar
DELETE FROM gate_logs 
WHERE plat_nomor IN (SELECT plat_nomor FROM vehicles);
```

#### E. Delete Logs Berdasarkan Waktu
```sql
-- Delete logs antara jam tertentu
DELETE FROM gate_logs 
WHERE TIME(entry_time) BETWEEN '08:00:00' AND '17:00:00';

-- Delete logs di luar jam kerja
DELETE FROM gate_logs 
WHERE TIME(entry_time) < '08:00:00' OR TIME(entry_time) > '17:00:00';
```

#### F. Delete Logs dengan Kombinasi Filter
```sql
-- Delete logs plat tidak terdaftar di bulan ini
DELETE FROM gate_logs 
WHERE plat_nomor NOT IN (SELECT plat_nomor FROM vehicles)
AND strftime('%Y-%m', entry_time) = strftime('%Y-%m', 'now');

-- Delete logs sebelum tanggal X kecuali plat tertentu
DELETE FROM gate_logs 
WHERE entry_time < '2026-05-01'
AND plat_nomor != 'DB4X';
```

---

### 3. 🔧 **Menggunakan API (untuk Developer)**

#### A. Delete All Logs
```bash
curl -X DELETE "http://localhost:5000/api/logs?all=true" \
  -H "Cookie: session=YOUR_SESSION_COOKIE"
```

#### B. Delete Logs by Date Range
```bash
curl -X DELETE "http://localhost:5000/api/logs?date_from=2026-05-01&date_to=2026-05-07" \
  -H "Cookie: session=YOUR_SESSION_COOKIE"
```

#### C. Delete Logs by Plate
```bash
curl -X DELETE "http://localhost:5000/api/logs?plat_nomor=DB1282WD" \
  -H "Cookie: session=YOUR_SESSION_COOKIE"
```

---

## 📊 Perbandingan Metode

| Metode | Kemudahan | Fleksibilitas | Keamanan |
|--------|-----------|---------------|----------|
| **Dashboard** | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐⭐ |
| **DB Browser** | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ |
| **API** | ⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ |

---

## ⚠️ PERINGATAN

### Sebelum Delete:
1. ✅ **Backup database** jika perlu:
   ```bash
   cp data/vehicles.db data/vehicles_backup_$(date +%Y%m%d).db
   ```

2. ✅ **Cek jumlah logs** yang akan dihapus:
   ```sql
   -- Cek total logs
   SELECT COUNT(*) FROM gate_logs;
   
   -- Cek logs yang akan dihapus (contoh: sebelum tanggal X)
   SELECT COUNT(*) FROM gate_logs WHERE entry_time < '2026-05-01';
   ```

3. ✅ **Test query dengan SELECT** dulu:
   ```sql
   -- Test dulu dengan SELECT
   SELECT * FROM gate_logs WHERE entry_time < '2026-05-01';
   
   -- Kalau sudah yakin, ganti SELECT dengan DELETE
   DELETE FROM gate_logs WHERE entry_time < '2026-05-01';
   ```

### Setelah Delete:
1. ✅ **Verify** logs sudah terhapus:
   ```sql
   SELECT COUNT(*) FROM gate_logs;
   ```

2. ✅ **Vacuum database** untuk reclaim space:
   ```sql
   VACUUM;
   ```

---

## 🔄 Restore dari Backup

Jika salah delete:
```bash
# Stop aplikasi dulu
# Restore dari backup
cp data/vehicles_backup_20260507.db data/vehicles.db
# Start aplikasi lagi
python app.py
```

---

## 📝 Query Berguna Lainnya

### View Logs
```sql
-- Lihat 10 logs terakhir
SELECT * FROM gate_logs ORDER BY entry_time DESC LIMIT 10;

-- Lihat logs hari ini
SELECT * FROM gate_logs WHERE DATE(entry_time) = DATE('now');

-- Lihat logs dengan nama pemilik
SELECT l.plat_nomor, l.entry_time, v.nama_pemilik
FROM gate_logs l
LEFT JOIN vehicles v ON l.plat_nomor = v.plat_nomor
ORDER BY l.entry_time DESC;
```

### Statistics
```sql
-- Total logs per plat
SELECT plat_nomor, COUNT(*) as total
FROM gate_logs
GROUP BY plat_nomor
ORDER BY total DESC;

-- Total logs per hari
SELECT DATE(entry_time) as tanggal, COUNT(*) as total
FROM gate_logs
GROUP BY DATE(entry_time)
ORDER BY tanggal DESC;

-- Total logs terdaftar vs tidak terdaftar
SELECT 
    CASE 
        WHEN plat_nomor IN (SELECT plat_nomor FROM vehicles) THEN 'Terdaftar'
        ELSE 'Tidak Terdaftar'
    END as status,
    COUNT(*) as total
FROM gate_logs
GROUP BY status;
```

---

## 🎯 Rekomendasi

### Untuk Penggunaan Sehari-hari:
✅ **Gunakan Dashboard** - Paling mudah dan aman

### Untuk Maintenance Rutin:
✅ **Gunakan DB Browser** - Lebih fleksibel untuk filter kompleks

### Untuk Automation:
✅ **Gunakan API** - Bisa dijadwalkan dengan cron job

---

## 🔐 Keamanan

### Dashboard:
- ✅ Require login
- ✅ Ada konfirmasi
- ✅ Rate limited (max 5 requests/minute)
- ✅ Logged (siapa yang delete)

### DB Browser:
- ⚠️ Direct access ke database
- ⚠️ Tidak ada audit log
- ⚠️ Bisa salah query

### API:
- ✅ Require authentication
- ✅ Rate limited
- ✅ Logged

---

## 📞 Support

Jika ada masalah:
1. Cek backup ada atau tidak
2. Cek server log untuk error
3. Restore dari backup jika perlu

---

**Rekomendasi:** Gunakan **Dashboard** untuk delete logs - paling mudah dan aman! 🎯
