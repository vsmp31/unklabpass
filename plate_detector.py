"""
plate_detector.py
─────────────────
Two-stage pipeline:
  1. YOLO (best.pt) — general object detection (draws colored boxes on everything)
  2. EasyOCR  — plate text reading (checks against lecturer DB)
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

# ── Eager-load both models at import time ─────────────────────────────────────
# This ensures they are ready before the first HTTP request arrives.
log.info("[YOLO] Loading custom best.pt…")
MODEL_PATH = os.path.join(os.path.dirname(__file__), "model", "best.pt")
_yolo: YOLO = YOLO(MODEL_PATH)
log.info("[YOLO] best.pt ready.")

log.info("[OCR] Loading EasyOCR…")
_reader: easyocr.Reader = easyocr.Reader(["en"], gpu=False, verbose=False)
log.info("[OCR] EasyOCR ready.")


def get_reader() -> easyocr.Reader:
    return _reader


def get_yolo() -> YOLO:
    return _yolo


# ── Image helpers ──────────────────────────────────────────────────────────────

def decode_b64(b64: str) -> np.ndarray:
    if "," in b64:
        b64 = b64.split(",", 1)[1]
    arr = np.frombuffer(base64.b64decode(b64), np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Cannot decode image")
    return img


# ── YOLO object detection ──────────────────────────────────────────────────────

def _boost_frame(img: np.ndarray) -> np.ndarray:
    """Brighten dark frames so YOLO can detect objects in low-light conditions."""
    mean_lum = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).mean()
    if mean_lum < 80:          # dark frame → apply CLAHE + brightness boost
        lab  = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        l     = clahe.apply(l)
        img   = cv2.cvtColor(cv2.merge([l, a, b]), cv2.COLOR_LAB2BGR)
    return img


def detect_objects(img: np.ndarray) -> list[dict]:
    """
    Run YOLOv8n on the frame (with dark-frame boost).
    Returns list of dicts: {x, y, w, h, label, class_name, class_id, conf, is_registered}
    """
    model  = get_yolo()
    bright = _boost_frame(img)
    results = model(bright, conf=0.10, verbose=False, imgsz=640)

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


# ── OCR + plate matching ───────────────────────────────────────────────────────

def ocr_frame(img: np.ndarray) -> str:
    """Run EasyOCR on the frame for plate text."""
    reader = get_reader()
    gray   = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # Upscale if image is small to improve OCR accuracy
    h, w = gray.shape[:2]
    if w < 300:
        scale = 300 / w
        gray = cv2.resize(gray, (0, 0), fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

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
    
    # Filter out expiration month/year (the 4 digits at the bottom)
    # Indonesian format: [1-2 Letters] [1-4 Digits] [0-3 Letters]
    match = re.search(r"([A-Z]{1,2})\s*(\d{1,4})\s*([A-Z]{0,3})", raw_text.upper())
    if match:
        cleaned = " ".join(g for g in match.groups() if g).strip()
        log.info(f"[OCR] Cleaned plate: {cleaned} (discarded year/bottom text)")
        return cleaned

    return raw_text


def normalize(text: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", text.upper())


def match_plate(text: str, lecturers: list[dict]) -> dict | None:
    ocr = normalize(text)
    if len(ocr) < 4:
        return None
    for lec in lecturers:
        db = normalize(lec.get("plate", ""))
        if not db:
            continue
        if ocr == db:
            return lec
        if len(ocr) >= 5 and len(db) >= 5 and (ocr in db or db in ocr):
            return lec
    return None


# ── Main entry point ───────────────────────────────────────────────────────────

def analyze_frame(b64_image: str, lecturers: list[dict]) -> dict:
    """
    1. Decode frame
    2. YOLO (best.pt) → detect license plates
    3. Crop detected plate region(s)
    4. EasyOCR → read text from cropped region
    5. Match against lecturer DB
    """
    img     = decode_b64(b64_image)
    fh, fw  = img.shape[:2]

    # ── Stage 1: object detection ─────────────────────────────────────────────
    yolo_boxes = detect_objects(img)

    # ── Stage 2: Crop & OCR ───────────────────────────────────────────────────
    ocr_text = ""
    matched = None

    if yolo_boxes:
        # Sort boxes by confidence descending
        sorted_boxes = sorted(yolo_boxes, key=lambda b: b.get("conf", 0.0), reverse=True)
        
        for box in sorted_boxes:
            bx, by, bw, bh = box["x"], box["y"], box["w"], box["h"]
            # Add padding (15% for more context)
            pad_x = int(bw * 0.15)
            pad_y = int(bh * 0.15)
            x1 = max(0, bx - pad_x)
            y1 = max(0, by - pad_y)
            x2 = min(fw, bx + bw + pad_x)
            y2 = min(fh, by + bh + pad_y)
            
            crop_img = img[y1:y2, x1:x2]
            if crop_img.size > 0:
                text = ocr_frame(crop_img)
                if text:
                    # Check if this plate matches DB
                    m = match_plate(text, lecturers)
                    if m:
                        matched = m
                        ocr_text = text
                        break
                    # Keep the first OCR text if no match found later
                    if not ocr_text:
                        ocr_text = text
                        
    else:
        # Fallback to full frame OCR if YOLO didn't find any plate
        ocr_text = ocr_frame(img)
        if ocr_text:
            matched = match_plate(ocr_text, lecturers)

    plate = matched["plate"] if matched else ocr_text

    # Flag all boxes as registered if matched (for frontend color)
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
