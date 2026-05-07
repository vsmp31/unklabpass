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

def _preprocess_frame(img: np.ndarray) -> np.ndarray:
    """
    Tingkatkan ketajaman (unsharp mask) dan brightness untuk motion blur & low-light
    """
    # 1. Unsharp mask (sharpening untuk motion blur ringan)
    blurred = cv2.GaussianBlur(img, (0, 0), 3)
    img = cv2.addWeighted(img, 1.5, blurred, -0.5, 0)
    
    # 2. CLAHE jika low-light
    mean_lum = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).mean()
    if mean_lum < 80:  # Frame gelap → apply CLAHE + brightness boost
        lab  = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        l     = clahe.apply(l)
        img   = cv2.cvtColor(cv2.merge([l, a, b]), cv2.COLOR_LAB2BGR)
    return img

def _nms(boxes: list[dict], iou_threshold: float = 0.5) -> list[dict]:
    """Non-maximum suppression untuk merge duplikat box"""
    if not boxes:
        return []
    
    # Sort berdasarkan confidence
    boxes = sorted(boxes, key=lambda b: b["conf"], reverse=True)
    kept = []
    
    def calculate_iou(box1, box2):
        x1_1, y1_1, x2_1, y2_1 = box1["_xyxy"]
        x1_2, y1_2, x2_2, y2_2 = box2["_xyxy"]
        
        xi1 = max(x1_1, x1_2)
        yi1 = max(y1_1, y1_2)
        xi2 = min(x2_1, x2_2)
        yi2 = min(y2_1, y2_2)
        inter_area = max(0, xi2 - xi1) * max(0, yi2 - yi1)
        
        box1_area = (x2_1 - x1_1) * (y2_1 - y1_1)
        box2_area = (x2_2 - x1_2) * (y2_2 - y1_2)
        union_area = box1_area + box2_area - inter_area
        
        return inter_area / union_area if union_area > 0 else 0
        
    for box in boxes:
        overlap = False
        for k_box in kept:
            if calculate_iou(box, k_box) > iou_threshold:
                overlap = True
                break
        if not overlap:
            kept.append(box)
            
    # Clean up _xyxy key
    for b in kept:
        b.pop("_xyxy", None)
    return kept

def _merge_results(result_lists, img_shape) -> list[dict]:
    """Merge boxes dari multiple inference passes."""
    all_boxes = []
    for results in result_lists:
        for r in results:
            for box in r.boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                cls_id   = int(box.cls[0])
                cls_name = r.names[cls_id]
                conf     = float(box.conf[0])
                all_boxes.append({
                    "x":             x1,
                    "y":             y1,
                    "w":             x2 - x1,
                    "h":             y2 - y1,
                    "label":         f"{cls_name} {int(conf * 100)}%",
                    "class_name":    cls_name,
                    "class_id":      cls_id,
                    "conf":          conf,
                    "is_registered": False,
                    "_xyxy":         (x1, y1, x2, y2)
                })
    return _nms(all_boxes, iou_threshold=0.5)


def detect_objects(img: np.ndarray) -> list[dict]:
    """
    Jalankan YOLOv8 pada frame (single scale untuk meminimalisir latency)
    Returns: list of dicts dengan info bounding box dan class
    """
    model  = get_yolo()
    bright = _preprocess_frame(img)
    
    # Pass 1: standard scale (kendaraan dekat/sedang) - Single pass for real-time speed!
    results = model(bright, conf=0.35, verbose=False, imgsz=640)
    
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
                "_xyxy":         (x1, y1, x2, y2)
            })
            
    return _nms(boxes, iou_threshold=0.5)


# ═══ OCR + Plate Matching ══════════════════════════════════════════════════════

def _prep_variants(crop: np.ndarray) -> list[np.ndarray]:
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    
    # --- Dynamic Illumination Adaptation ---
    mean_brightness = np.mean(gray)
    if mean_brightness < 80:
        # Terlalu gelap (malam hari) -> Terapkan Gamma Correction untuk menerangkan
        gamma = 1.5
        invGamma = 1.0 / gamma
        table = np.array([((i / 255.0) ** invGamma) * 255 for i in np.arange(0, 256)]).astype("uint8")
        gray = cv2.LUT(gray, table)
    elif mean_brightness > 200:
        # Terlalu silau (glare) -> Terapkan Thresholding untuk meredam putih
        _, gray = cv2.threshold(gray, 200, 255, cv2.THRESH_TRUNC)
        
    # SPEED: Resize 600px (dari 800px) untuk balance speed & accuracy
    h, w = gray.shape[:2]
    if w < 600:
        scale = 600 / w
        gray = cv2.resize(gray, (0, 0), fx=scale, fy=scale, interpolation=cv2.INTER_LANCZOS4)
    
    # SPEED: Denoise cepat
    denoised = cv2.fastNlMeansDenoising(gray, None, h=7, templateWindowSize=5, searchWindowSize=15)
    
    # Morphological operations untuk perbaiki karakter
    kernel_rect = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    kernel_sharp = np.array([[-1,-1,-1],[-1,9,-1],[-1,-1,-1]])
        
    # SPEED: Hanya 2 variants terbaik (dari 5)
    # V1: CLAHE + sharpen (terbaik untuk berbagai kondisi)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(4,4))
    clahe_img = clahe.apply(denoised)
    v1 = cv2.filter2D(clahe_img, -1, kernel_sharp)
    v1 = cv2.morphologyEx(v1, cv2.MORPH_CLOSE, kernel_rect)
    
    # V2: Adaptive threshold (bagus untuk lighting tidak merata)
    v2 = cv2.adaptiveThreshold(denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
    v2 = cv2.morphologyEx(v2, cv2.MORPH_CLOSE, kernel_rect)
    
    return [v1, v2]  # Hanya 2 variants untuk SPEED!

def ocr_frame(img: np.ndarray) -> tuple[str, str, float]:
    """
    Jalankan EasyOCR pada frame dengan 4 preprocessing variant
    Returns: (cleaned_text, raw_text, confidence)
    """
    reader = get_reader()
    best_text = ""
    best_conf = 0.0
    best_raw = ""
    
    # Character confusion mapping (common OCR mistakes)
    confusion_map = {
        '0': ['O', 'D', 'Q'],
        'O': ['0', 'D', 'Q'],
        '1': ['I', 'L', '7'],
        'I': ['1', 'L', '7'],
        '8': ['B', '3', '6'],
        'B': ['8', '3', '6'],
        '5': ['S', '6'],
        'S': ['5', '6'],
        '2': ['Z'],
        'Z': ['2'],
    }
    
    all_candidates = []  # Store all possible readings
    
    for variant in _prep_variants(img):
        result = reader.readtext(
            variant,
            allowlist="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 ",
            detail=1, paragraph=False,
        )
        if not result:
            continue
            
        avg_conf = sum(r[2] for r in result) / len(result)
        raw = " ".join(r[1] for r in result if r[2] >= 0.10).strip()
        
        # PERBAIKAN: Regex STRICT - minimal 3 angka!
        patterns = [
            r"([A-Z]{1,2})\s*(\d{3,4})\s*([A-Z]{1,3})",  # DB 1482 WD (STRICT: 3-4 angka)
            r"([A-Z]{2})[\s\-]*(\d{3,4})[\s\-]*([A-Z]{1,2})",  # Dengan dash
        ]
        
        for pattern in patterns:
            match = re.search(pattern, raw.upper())
            if match:
                # Gabungkan tanpa spasi
                candidate = "".join(g for g in match.groups() if g)
                
                # VALIDASI: Pastikan ada minimal 3 angka
                digit_count = sum(c.isdigit() for c in candidate)
                if digit_count >= 3:  # Minimal 3 angka
                    all_candidates.append({
                        'text': candidate,
                        'conf': avg_conf,
                        'raw': raw.upper()
                    })
                    
                    if avg_conf > best_conf:
                        best_text = candidate
                        best_conf = avg_conf
                        best_raw = raw.upper()
                break
    
    # PERBAIKAN: Jika ada multiple candidates, pilih yang paling konsisten
    if len(all_candidates) > 1:
        # Group similar candidates (dengan toleransi 1-2 karakter berbeda)
        from collections import Counter
        
        # Extract number part untuk comparison
        number_parts = []
        for c in all_candidates:
            # Extract angka dari plat (misal: DB1482WD -> 1482)
            nums = re.findall(r'\d+', c['text'])
            if nums:
                number_parts.append((nums[0], c))
        
        if number_parts:
            # Cari angka yang paling sering muncul
            num_counter = Counter([n[0] for n in number_parts])
            most_common_num = num_counter.most_common(1)[0][0]
            
            # Pilih candidate dengan angka paling umum dan confidence tertinggi
            best_candidate = max(
                [c for n, c in number_parts if n == most_common_num],
                key=lambda x: x['conf']
            )
            best_text = best_candidate['text']
            best_conf = best_candidate['conf']
            best_raw = best_candidate['raw']
            
    if best_text:
        log.info(f"[OCR] Cleaned plate: {best_text} (conf: {best_conf:.2f}, raw: {best_raw}, candidates: {len(all_candidates)})")
    else:
        log.warning(f"[OCR] Failed to extract plate. Raw: {best_raw}")
        
    return best_text, best_raw, best_conf


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

def _blur_score(img: np.ndarray) -> float:
    """Laplacian variance — semakin tinggi = semakin tajam"""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return cv2.Laplacian(gray, cv2.CV_64F).var()

def select_sharpest_frames(images: list[np.ndarray], top_n: int = 2) -> list[np.ndarray]:
    """Pilih N frame paling tajam dari vector untuk di-analyze"""
    if not images:
        return []
    scored = [(img, _blur_score(img)) for img in images]
    scored.sort(key=lambda x: x[1], reverse=True)
    return [img for img, _ in scored[:top_n]]

def analyze_frame_from_img(img: np.ndarray, lecturers: list[dict]) -> dict:
    """
    Pipeline lengkap untuk analyze frame (numpy array):
    """
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
            # Tambah padding 25% untuk context OCR yang lebih baik
            pad_x = int(bw * 0.25)
            pad_y = int(bh * 0.25)
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

def analyze_frame(b64_image: str, lecturers: list[dict]) -> dict:
    """Wrapper fungsi lama untuk backward compatibility jika diperlukan"""
    img = decode_b64(b64_image)
    return analyze_frame_from_img(img, lecturers)

def analyze_crop(b64_image: str, lecturers: list[dict]) -> dict:
    """
    Hanya jalankan OCR dan Matching pada gambar potongan plat (crop)
    """
    img = decode_b64(b64_image)
    if img is None:
        return {"found": False, "raw_text": ""}
        
    # Resize image to standard width (400px) to help OCR
    h, w = img.shape[:2]
    if w > 0 and w < 400:
        new_w = 400
        new_h = int(h * (new_w / w))
        img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_CUBIC)

    # --- ROI Cropping: Buang 20% bagian bawah (area tanggal pajak) ---
    h_new = img.shape[0]
    img = img[:int(h_new * 0.80), :]

    ocr_text, raw_text, conf = ocr_frame(img)
    matched = match_plate(ocr_text, lecturers) if ocr_text else None
    
    return {
        "found":      bool(ocr_text),
        "registered": matched is not None,
        "plate":      matched["plate"] if matched else ocr_text,
        "raw_text":   raw_text,
        "lecturer":   matched
    }
