import streamlit as st
import numpy as np
import time
import json
import base64
import os
from PIL import Image


# ─── helpers ──────────────────────────────────────────────────────────────────

def _b64(path: str) -> str:
    with open(path, "rb") as f:
        data = f.read()
    ext = os.path.splitext(path)[-1].lstrip(".").replace("jpg", "jpeg")
    return f"data:image/{ext};base64,{base64.b64encode(data).decode()}"


def _read_template(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


# ─── CSS ──────────────────────────────────────────────────────────────────────

def apply_custom_css():
    bg = _b64("templates/unklab.jpg")
    css = _read_template("templates/styles.css").replace("__BG_IMAGE__", bg)
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


# ─── Navbar ───────────────────────────────────────────────────────────────────

def render_navbar(page: str = "home"):
    logo = _b64("templates/unklabpass.png")
    navbar_html = _read_template("templates/header.html")
    navbar_html = navbar_html.replace("__LOGO__", logo)
    navbar_html = navbar_html.replace("__HOME_CLASS__", "active" if page == "home" else "")
    navbar_html = navbar_html.replace("__ABOUT_CLASS__", "active" if page == "about" else "")
    st.markdown(navbar_html, unsafe_allow_html=True)


# ─── Home page ────────────────────────────────────────────────────────────────

def render_home_page():
    left_col, right_col = st.columns([1.5, 1], gap="medium")

    cam_image = None
    uploaded = None

    # ── LEFT COLUMN ──────────────────────────────────────────────────────────
    with left_col:
        # Camera section
        st.markdown('<p class="section-title">📹 Live Camera</p>', unsafe_allow_html=True)
        st.markdown('<p class="section-subtitle">Klik "Start Camera" untuk memulai</p>', unsafe_allow_html=True)
        cam_image = st.camera_input("cam", label_visibility="collapsed")

        # Preview & Controls section
        prev_col, ctrl_col = st.columns([1, 1], gap="small")

        with prev_col:
            preview = st.session_state.get("preview_image")
            if preview is not None:
                st.image(preview, use_container_width=True)
            else:
                st.markdown('''
                    <div class="preview-container">
                        <div class="preview-placeholder">Belum ada gambar</div>
                    </div>
                ''', unsafe_allow_html=True)

        with ctrl_col:
            # Analyze button
            if st.button("🔍 Analisa Plat Dosen", use_container_width=True, key="analyze_btn"):
                with st.spinner("Menganalisa plat nomor..."):
                    time.sleep(1.5)
                    try:
                        with open("data/lecturers.json") as f:
                            data = json.load(f)
                        st.session_state.detected = np.random.choice(data)
                        st.session_state.scan_time = time.strftime("%Y-%m-%d %H:%M:%S")
                        st.success("✅ Analisa selesai!")
                        time.sleep(0.5)
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Error: {e}")

            # Upload section
            fname = st.session_state.get("uploaded_name", "")
            hint = f"📄 {fname}" if fname else "📤 Upload gambar plat nomor"
            st.markdown(f'<p class="upload-hint">{hint}</p>', unsafe_allow_html=True)
            
            uploaded = st.file_uploader(
                "up",
                type=["jpg", "png", "jpeg"],
                label_visibility="collapsed",
                help="Upload gambar plat nomor",
            )

    # ── RIGHT COLUMN ─────────────────────────────────────────────────────────
    with right_col:
        detected = st.session_state.get("detected")
        nomor   = detected["plate"]                    if detected else "—"
        merek   = detected.get("department", "—")      if detected else "—"
        pemilik = detected["name"]                     if detected else "—"
        tgl     = st.session_state.get("scan_time", "—")
        akurasi = f"{np.random.randint(88, 99)}%"     if detected else "—"

        if detected:
            cap_inner = (
                f'<div class="success-badge">✓ Terdeteksi</div>'
                f'<div class="plate-number">{nomor}</div>'
            )
        else:
            cap_inner = '<div class="waiting-text">Menunggu hasil analisa...<br><span style="font-size:0.9rem;opacity:0.6;">Silakan ambil foto atau upload gambar</span></div>'

        card = _read_template("templates/analytics.html")
        card = card.replace("__CAPTURE__", cap_inner)
        card = card.replace("__NOMOR__", nomor)
        card = card.replace("__MEREK__", merek)
        card = card.replace("__PEMILIK__", pemilik)
        card = card.replace("__TANGGAL__", tgl)
        card = card.replace("__AKURASI__", akurasi)
        st.markdown(card, unsafe_allow_html=True)

    # ── Update preview state ─────────────────────────────────────────────────
    new_img = None
    new_id  = None
    if cam_image is not None:
        new_img = Image.open(cam_image)
        new_id  = cam_image.file_id
    elif uploaded is not None:
        new_img = Image.open(uploaded)
        new_id  = uploaded.name + str(uploaded.size)
        st.session_state.uploaded_name = uploaded.name

    if new_img is not None and st.session_state.get("_prev_id") != new_id:
        st.session_state.preview_image = new_img
        st.session_state._prev_id      = new_id
        st.rerun()


# ─── About page ───────────────────────────────────────────────────────────────

def render_about_page():
    st.markdown(
        '<section class="about-shell">'
        '<h1 class="about-title">Tentang UnklabPass</h1>'
        '<p class="about-body">'
        'UnklabPass adalah sistem identifikasi kendaraan berbasis AI untuk Universitas Klabat.<br><br>'
        'Menggunakan Computer Vision dan OCR untuk mendeteksi plat nomor secara real-time '
        'dan mencocokkannya dengan database dosen yang terdaftar.<br><br>'
        '<em style="opacity:0.55;">Halaman ini masih dalam pengembangan.</em>'
        '</p>'
        '</section>',
        unsafe_allow_html=True,
    )


# ─── Footer (intentionally empty) ────────────────────────────────────────────

def render_footer():
    pass
