"""
plate_detector.py
─────────────────
Pipeline 2 tahap untuk deteksi plat nomor:
  1. YOLOv8 (best.pt) — deteksi objek umum (gambar kotak berwarna pada semua objek)
  2. EasyOCR — baca text plat nomor (cek dengan database kendaraan terdaftar)
"""

import cv2
import numpy as np
import easyocr
import base64
import re
import logging
import os
from ultralytics import YOLO

log = logging.getLogger(__name__)

# ═══ Load Model saat Import (Eager Loading) ═══════════════════════════════════
# Memastikan model sudah siap sebelum HTTP request pertama datang
log.info("[YOLO] Loading custom best.pt…")
MODEL_PATH = os.path.join(os.path.dirname(__file__), "model", "best.pt")
_yolo: YOLO = YOLO(MODEL_PATH)
log.info("[YOLO] best.pt ready.")

log.info("[OCR] Loading EasyOCR…")
_reader: easyocr.Reader = easyocr.Reader(["en"], gpu=False, verbose=False)
log.info("[OCR] EasyOCR ready.")


def get_reader() -> easyocr.Reader:
    """Return instance EasyOCR reader yang sudah di-load"""
    return _reader


def get_yolo() -> YOLO:
    """Return instance YOLO model yang sudah di-load"""
    return _yolo


# ═══ Helper Functions untuk Image Processing ══════════════════════════════════

def decode_b64(b64: str) -> np.ndarray:
    """Decode base64 string menjadi OpenCV image (numpy array)"""
    if "," in b64:
        b64 = b64.split(",", 1)[1]  # Remove data:image/jpeg;base64, prefix
    arr = np.frombuffer(base64.b64decode(b64), np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Cannot decode image")
    return img


# ═══ YOLO Object Detection ════════════════════════════════════════════════════

def _boost_frame(img: np.ndarray) -> np.ndarray:
    """
    Tingkatkan brightness frame gelap agar YOLO bisa deteksi objek di kondisi low-light
    Menggunakan CLAHE (Contrast Limited Adaptive Histogram Equalization)
    """
    mean_lum = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).mean()
    if mean_lum < 80:  # Frame gelap → apply CLAHE + brightness boost
        lab  = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        l     = clahe.apply(l)
        img   = cv2.cvtColor(cv2.merge([l, a, b]), cv2.COLOR_LAB2BGR)
    return img


def detect_objects(img: np.ndarray) -> list[dict]:
    """
    Jalankan YOLOv8 pada frame (dengan boost untuk frame gelap)
    Returns: list of dicts dengan info bounding box dan class
    Format: {x, y, w, h, label, class_name, class_id, conf, is_registered}
    """
    model  = get_yolo()
    bright = _boost_frame(img)
    results = model(bright, conf=0.45, verbose=False, imgsz=640)

    boxes: list[dict] = []
    for r in results:
        for box in r.boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
            cls_id   = int(box.cls[0])
            cls_name = r.names[cls_id]
            conf     = float(box.conf[0])
            boxes.append({
                "x":             x1,
                "y":             y1,
                "w":             x2 - x1,
                "h":             y2 - y1,
                "label":         f"{cls_name} {int(conf * 100)}%",
                "class_name":    cls_name,
                "class_id":      cls_id,
                "conf":          conf,
                "is_registered": False,
            })
    return boxes


# ═══ OCR + Plate Matching ══════════════════════════════════════════════════════

def ocr_frame(img: np.ndarray) -> str:
    """
    Jalankan EasyOCR pada frame untuk baca text plat nomor
    Returns: cleaned plate text (format: DB1234ABC)
    """
    reader = get_reader()
    gray   = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # Upscale jika image terlalu kecil untuk improve akurasi OCR
    h, w = gray.shape[:2]
    if w < 300:
        scale = 300 / w
        gray = cv2.resize(gray, (0, 0), fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

    # Jalankan OCR dengan allowlist karakter plat nomor
    result = reader.readtext(
        gray,
        allowlist="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 ",
        detail=1, paragraph=False,
    )
    
    if result:
        log.info(f"[OCR] Raw results: {[(r[1], round(r[2], 2)) for r in result]}")
    else:
        log.info("[OCR] No text detected.")

    raw_text = " ".join(r[1] for r in result if r[2] >= 0.10).strip()
    
    # Strictly match format plat 'DB' dan buang tahun kadaluarsa
    match = re.search(r"(DB)\s*(\d{1,4})\s*([A-Z]{0,3})", raw_text.upper())
    if match:
        cleaned = "".join(g for g in match.groups() if g).strip()
        log.info(f"[OCR] Cleaned DB plate: {cleaned}")
        return cleaned

    return ""


def match_plate(text: str, lecturers: list[dict]) -> dict | None:
    """
    Cocokkan text OCR dengan database kendaraan terdaftar
    Menggunakan Levenshtein Distance untuk toleransi 1 karakter salah
    Returns: dict vehicle data jika match, None jika tidak
    """
    ocr = text
    if len(ocr) < 4:
        return None
    
    # Fungsi hitung Levenshtein Distance (edit distance)
    def levenshtein(s1: str, s2: str) -> int:
        if len(s1) < len(s2):
            return levenshtein(s2, s1)
        if len(s2) == 0:
            return len(s1)
        prev_row = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            curr_row = [i + 1]
            for j, c2 in enumerate(s2):
                ins = prev_row[j + 1] + 1
                dl  = curr_row[j] + 1
                sub = prev_row[j] + (c1 != c2)
                curr_row.append(min(ins, dl, sub))
            prev_row = curr_row
        return prev_row[-1]

    # Loop semua kendaraan di database
    for lec in lecturers:
        db = lec.get("plate", "")
        if not db:
            continue
        
        # Exact match
        if ocr == db:
            return lec
        
        # Toleransi 1 karakter meleset untuk plat >= 6 digit
        if len(ocr) >= 6 and len(db) >= 6 and levenshtein(ocr, db) <= 1:
            return lec
        
        # Substring match untuk plat >= 5 digit
        if len(ocr) >= 5 and len(db) >= 5 and (ocr in db or db in ocr):
            return lec
            
    return None


# ═══ Main Entry Point ══════════════════════════════════════════════════════════

def analyze_frame(b64_image: str, lecturers: list[dict]) -> dict:
    """
    Pipeline lengkap untuk analyze frame:
    1. Decode base64 image
    2. YOLO (best.pt) → deteksi plat nomor
    3. Crop region plat yang terdeteksi
    4. EasyOCR → baca text dari cropped region
    5. Match dengan database kendaraan terdaftar
    
    Returns: dict dengan info hasil deteksi dan matching
    """
    img     = decode_b64(b64_image)
    fh, fw  = img.shape[:2]

    # ═══ Stage 1: Object Detection dengan YOLO ════════════════════════════════
    yolo_boxes = detect_objects(img)

    # ═══ Stage 2: Crop & OCR ══════════════════════════════════════════════════
    ocr_text = ""
    matched = None

    if yolo_boxes:
        # Sort boxes berdasarkan confidence (tertinggi dulu)
        sorted_boxes = sorted(yolo_boxes, key=lambda b: b.get("conf", 0.0), reverse=True)
        
        for box in sorted_boxes:
            bx, by, bw, bh = box["x"], box["y"], box["w"], box["h"]
            # Tambah padding 15% untuk context lebih baik
            pad_x = int(bw * 0.15)
            pad_y = int(bh * 0.15)
            x1 = max(0, bx - pad_x)
            y1 = max(0, by - pad_y)
            x2 = min(fw, bx + bw + pad_x)
            y2 = min(fh, by + bh + pad_y)
            
            # Crop region plat
            crop_img = img[y1:y2, x1:x2]
            if crop_img.size > 0:
                text = ocr_frame(crop_img)
                if text:
                    # Cek apakah plat ini match dengan database
                    m = match_plate(text, lecturers)
                    if m:
                        matched = m
                        ocr_text = text
                        break  # Stop jika sudah ketemu match
                    # Simpan OCR text pertama jika tidak ada match
                    if not ocr_text:
                        ocr_text = text
                        
    else:
        # Fallback: OCR full frame jika YOLO tidak deteksi plat
        ocr_text = ocr_frame(img)
        if ocr_text:
            matched = match_plate(ocr_text, lecturers)

    # Ambil plat nomor dari matched vehicle atau OCR text
    plate = matched["plate"] if matched else ocr_text

    # Flag semua boxes sebagai registered jika match (untuk warna di frontend)
    if matched:
        for box in yolo_boxes:
            box["is_registered"] = True

    return {
        "found":      len(yolo_boxes) > 0 or bool(ocr_text),
        "registered": matched is not None,
        "plate":      plate,
        "lecturer":   matched,
        "boxes":      yolo_boxes,
        "frame_size": [fw, fh],
    }
