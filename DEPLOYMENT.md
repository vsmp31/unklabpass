# 🚀 Panduan Deployment UnklabPass ke Production Server

## 📋 Daftar Isi
1. [Persiapan Server](#persiapan-server)
2. [Konfigurasi Database SQLite](#konfigurasi-database-sqlite)
3. [Setup OCR & YOLO](#setup-ocr--yolo)
4. [Deployment Steps](#deployment-steps)
5. [Troubleshooting](#troubleshooting)

---

## 🖥️ Persiapan Server

### Minimum Requirements
- **OS**: Ubuntu 20.04+ / Debian 11+ / CentOS 8+
- **RAM**: 4GB minimum (8GB recommended untuk YOLO + OCR)
- **CPU**: 2 cores minimum (4 cores recommended)
- **Storage**: 10GB free space
- **Python**: 3.9 - 3.11

### Install System Dependencies

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Python & build tools
sudo apt install -y python3 python3-pip python3-venv python3-dev

# Install OpenCV dependencies
sudo apt install -y libgl1-mesa-glx libglib2.0-0 libsm6 libxext6 libxrender-dev

# Install Git
sudo apt install -y git

# Install Nginx (optional, untuk reverse proxy)
sudo apt install -y nginx
```

---

## 🗄️ Konfigurasi Database SQLite

### ✅ SQLite AMAN untuk Production!

**SQLite cocok untuk aplikasi ini karena:**
- ✅ **Single-file database** - mudah backup & restore
- ✅ **No server process** - tidak perlu manage database daemon
- ✅ **ACID compliant** - data consistency terjamin
- ✅ **Fast reads** - perfect untuk read-heavy workload
- ✅ **Low maintenance** - zero configuration
- ✅ **Concurrent reads** - multiple users bisa read bersamaan

**Limitasi yang perlu diperhatikan:**
- ⚠️ **Write concurrency** - hanya 1 write operation pada satu waktu
- ⚠️ **File locking** - pastikan filesystem support file locking (ext4, xfs OK)
- ⚠️ **Network storage** - JANGAN taruh di NFS/SMB (gunakan local disk)

### Database Setup

```bash
# Buat direktori data jika belum ada
mkdir -p data

# Set permissions
chmod 755 data

# Database akan auto-create saat first run
# File: data/vehicles.db
```

### Database Backup Strategy

```bash
# Backup manual
sqlite3 data/vehicles.db ".backup data/vehicles_backup_$(date +%Y%m%d).db"

# Backup otomatis dengan cron (setiap hari jam 2 pagi)
crontab -e
# Tambahkan:
0 2 * * * cd /path/to/app && sqlite3 data/vehicles.db ".backup data/vehicles_backup_$(date +\%Y\%m\%d).db"
```

### Database Optimization

File `app.py` sudah include optimizations:
- ✅ **Indexes** pada kolom yang sering di-query
- ✅ **In-memory cache** untuk vehicle lookup
- ✅ **Connection pooling** via Flask context
- ✅ **Prepared statements** untuk prevent SQL injection

---

## 🤖 Setup OCR & YOLO

### Model Files

**YOLO Model** (`model/best.pt`):
- ✅ Sudah ada di project
- ✅ Loaded saat startup (eager loading)
- ✅ Shared across all workers (preload_app=True)

**EasyOCR Model**:
- ⚠️ **First run akan download model** (~100MB)
- ⚠️ Model disimpan di `~/.EasyOCR/model/`
- ✅ Setelah download, tidak perlu internet lagi

### Pre-download OCR Model (Recommended)

```bash
# Jalankan script ini untuk download model sebelum production
python3 << EOF
import easyocr
reader = easyocr.Reader(['en'], gpu=False, verbose=True)
print("✅ EasyOCR model downloaded successfully!")
EOF
```

### GPU vs CPU

**Default: CPU Mode** (sudah dikonfigurasi)
```python
# plate_detector.py
_reader = easyocr.Reader(["en"], gpu=False, verbose=False)
```

**Jika server punya GPU NVIDIA:**
```bash
# Install CUDA toolkit
# https://developer.nvidia.com/cuda-downloads

# Install PyTorch with CUDA
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118

# Ubah di plate_detector.py:
_reader = easyocr.Reader(["en"], gpu=True, verbose=False)
```

### Memory Considerations

**YOLO + OCR Memory Usage:**
- YOLO model: ~50MB
- EasyOCR model: ~100MB
- Per-request processing: ~200-500MB (temporary)

**Recommended Gunicorn Config:**
```python
# gunicorn_config.py
workers = 2  # Untuk server 4GB RAM
workers = 4  # Untuk server 8GB RAM
```

---

## 🚀 Deployment Steps

### 1. Clone & Setup Project

```bash
# Clone repository
git clone <your-repo-url> unklabpass
cd unklabpass

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

### 2. Environment Configuration

```bash
# Copy example env file
cp .env.example .env

# Edit .env dengan editor favorit
nano .env

# PENTING: Ganti SECRET_KEY dengan random string!
# Generate dengan:
python3 -c "import secrets; print(secrets.token_hex(32))"
```

### 3. Create Logs Directory

```bash
mkdir -p logs
chmod 755 logs
```

### 4. Test Run (Development Mode)

```bash
# Test apakah aplikasi berjalan
python3 app.py

# Akses di browser: http://localhost:5000
# Ctrl+C untuk stop
```

### 5. Production Run dengan Gunicorn

```bash
# Run dengan Gunicorn
gunicorn -c gunicorn_config.py wsgi:app

# Atau run di background dengan nohup
nohup gunicorn -c gunicorn_config.py wsgi:app > logs/gunicorn.log 2>&1 &

# Check process
ps aux | grep gunicorn
```

### 6. Setup Systemd Service (Recommended)

```bash
# Create service file
sudo nano /etc/systemd/system/unklabpass.service
```

Paste konfigurasi ini:

```ini
[Unit]
Description=UnklabPass Vehicle Recognition System
After=network.target

[Service]
Type=notify
User=www-data
Group=www-data
WorkingDirectory=/path/to/unklabpass
Environment="PATH=/path/to/unklabpass/venv/bin"
ExecStart=/path/to/unklabpass/venv/bin/gunicorn -c gunicorn_config.py wsgi:app
ExecReload=/bin/kill -s HUP $MAINPID
KillMode=mixed
TimeoutStopSec=5
PrivateTmp=true
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable & start service:

```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable auto-start on boot
sudo systemctl enable unklabpass

# Start service
sudo systemctl start unklabpass

# Check status
sudo systemctl status unklabpass

# View logs
sudo journalctl -u unklabpass -f
```

### 7. Setup Nginx Reverse Proxy (Optional)

```bash
# Create Nginx config
sudo nano /etc/nginx/sites-available/unklabpass
```

Paste konfigurasi ini:

```nginx
server {
    listen 80;
    server_name your-domain.com;  # Ganti dengan domain Anda

    client_max_body_size 10M;  # Max upload size untuk image

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Timeout untuk OCR processing
        proxy_connect_timeout 120s;
        proxy_send_timeout 120s;
        proxy_read_timeout 120s;
    }

    location /static {
        alias /path/to/unklabpass/static;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }
}
```

Enable site:

```bash
# Create symlink
sudo ln -s /etc/nginx/sites-available/unklabpass /etc/nginx/sites-enabled/

# Test config
sudo nginx -t

# Reload Nginx
sudo systemctl reload nginx
```

### 8. Setup SSL dengan Let's Encrypt (Recommended)

```bash
# Install Certbot
sudo apt install -y certbot python3-certbot-nginx

# Get SSL certificate
sudo certbot --nginx -d your-domain.com

# Auto-renewal sudah disetup oleh Certbot
```

---

## 🔧 Troubleshooting

### Database Issues

**Error: "database is locked"**
```bash
# Check file permissions
ls -la data/vehicles.db

# Fix permissions
chmod 644 data/vehicles.db
chown www-data:www-data data/vehicles.db

# Check for stale lock files
rm -f data/vehicles.db-shm data/vehicles.db-wal
```

**Database corruption**
```bash
# Check integrity
sqlite3 data/vehicles.db "PRAGMA integrity_check;"

# Restore from backup
cp data/vehicles_backup_YYYYMMDD.db data/vehicles.db
```

### OCR/YOLO Issues

**Error: "Cannot load model"**
```bash
# Check model file exists
ls -la model/best.pt

# Check EasyOCR model
ls -la ~/.EasyOCR/model/

# Re-download OCR model
rm -rf ~/.EasyOCR/model/
python3 -c "import easyocr; easyocr.Reader(['en'], gpu=False)"
```

**High memory usage**
```bash
# Reduce Gunicorn workers
# Edit gunicorn_config.py:
workers = 2  # Reduce from 4 to 2

# Restart service
sudo systemctl restart unklabpass
```

### Performance Issues

**Slow response time**
```bash
# Check CPU usage
top

# Check memory
free -h

# Check disk I/O
iostat -x 1

# View application logs
tail -f logs/error.log
```

**Too many requests**
```bash
# Add rate limiting di Nginx
# Edit /etc/nginx/sites-available/unklabpass

limit_req_zone $binary_remote_addr zone=api:10m rate=10r/s;

location /analyze {
    limit_req zone=api burst=20 nodelay;
    proxy_pass http://127.0.0.1:5000;
}
```

### Service Management

```bash
# Restart service
sudo systemctl restart unklabpass

# Stop service
sudo systemctl stop unklabpass

# View logs
sudo journalctl -u unklabpass -n 100 --no-pager

# Follow logs real-time
sudo journalctl -u unklabpass -f
```

---

## 📊 Monitoring

### Log Files

```bash
# Application logs
tail -f logs/error.log
tail -f logs/access.log

# System logs
sudo journalctl -u unklabpass -f

# Nginx logs
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```

### Health Check Endpoint

Tambahkan di `app.py`:

```python
@app.route("/health")
def health():
    return jsonify({
        "status": "healthy",
        "database": os.path.exists(DB_PATH),
        "model": os.path.exists(MODEL_PATH)
    })
```

### Monitoring Script

```bash
# Create monitoring script
nano monitor.sh
```

```bash
#!/bin/bash
# Simple health check script

URL="http://localhost:5000/health"
RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" $URL)

if [ $RESPONSE -eq 200 ]; then
    echo "✅ Service is healthy"
else
    echo "❌ Service is down! Restarting..."
    sudo systemctl restart unklabpass
fi
```

```bash
# Make executable
chmod +x monitor.sh

# Add to cron (check every 5 minutes)
crontab -e
# Add:
*/5 * * * * /path/to/monitor.sh >> /path/to/logs/monitor.log 2>&1
```

---

## 🎯 Production Checklist

- [ ] SECRET_KEY diganti dengan random string
- [ ] Debug mode dimatikan (FLASK_ENV=production)
- [ ] Database backup strategy disetup
- [ ] Gunicorn service running dengan systemd
- [ ] Nginx reverse proxy configured
- [ ] SSL certificate installed
- [ ] Firewall configured (allow 80, 443)
- [ ] Log rotation setup
- [ ] Monitoring script active
- [ ] Health check endpoint working
- [ ] Default admin password diganti

---

## 📞 Support

Jika ada masalah deployment, check:
1. Application logs: `logs/error.log`
2. System logs: `sudo journalctl -u unklabpass`
3. Nginx logs: `/var/log/nginx/error.log`

**Common Issues:**
- Database locked → Check permissions & file locking
- Model not found → Check model files exist
- High memory → Reduce Gunicorn workers
- Slow OCR → Consider GPU acceleration

---

**Good luck with your deployment! 🚀**
