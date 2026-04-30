"""
Gunicorn Configuration untuk Production
"""
import multiprocessing
import os

# Server Socket
bind = f"0.0.0.0:{os.getenv('PORT', '5000')}"
backlog = 2048

# Worker Processes
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = 'gevent'  # Async worker untuk handle banyak koneksi
worker_connections = 1000
timeout = 120  # Timeout 120 detik untuk OCR & YOLO processing
keepalive = 5

# Logging
accesslog = 'logs/access.log'
errorlog = 'logs/error.log'
loglevel = 'info'
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process Naming
proc_name = 'unklabpass'

# Server Mechanics
daemon = False
pidfile = 'logs/gunicorn.pid'
umask = 0
user = None
group = None
tmp_upload_dir = None

# SSL (jika menggunakan HTTPS)
# keyfile = '/path/to/keyfile'
# certfile = '/path/to/certfile'

# Preload app untuk load model sekali saja
preload_app = True

# Graceful timeout
graceful_timeout = 30

# Max requests per worker (restart worker setelah N requests untuk prevent memory leak)
max_requests = 1000
max_requests_jitter = 50
