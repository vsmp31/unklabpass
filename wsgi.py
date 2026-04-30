"""
WSGI Entry Point untuk Production Server
Digunakan oleh Gunicorn untuk menjalankan aplikasi Flask
"""
from app import app

if __name__ == "__main__":
    app.run()
