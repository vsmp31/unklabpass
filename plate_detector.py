"""
plate_detector.py
─────────────────
Two-stage pipeline:
  1. YOLOv8n  — general object detection (draws colored boxes on everything)
  2. EasyOCR  — plate text reading (checks against lecturer DB)
"""

import cv2
import numpy as np
import easyocr
import base64
import re
import logging
from ultralytics import YOLO

log = logging.getLogger(__name__)

# ── Eager-load both models at import time ─────────────────────────────────────
# This ensures they are ready before the first HTTP request arrives.
log.info("[YOLO] Loading YOLOv8n…")
_yolo: YOLO = YOLO("yolov8n.pt")    # ~6 MB, auto-downloaded on first run
log.info("[YOLO] YOLOv8n ready.")

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
    results = model(bright, conf=0.20, verbose=False, imgsz=640)

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
    """Run EasyOCR on the full (grayscaled) frame for plate text."""
    reader = get_reader()
    gray   = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    result = reader.readtext(
        gray,
        allowlist="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 ",
        detail=1, paragraph=False,
    )
    return " ".join(r[1] for r in result if r[2] >= 0.20).strip()


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
    2. YOLOv8 → detect all objects (boxes always populated)
    3. EasyOCR → try to read plate text from full frame
    4. Match against lecturer DB
    Returns structured result for the Flask API.
    """
    img     = decode_b64(b64_image)
    fh, fw  = img.shape[:2]

    # ── Stage 1: object detection ─────────────────────────────────────────────
    yolo_boxes = detect_objects(img)

    # ── Stage 2: plate OCR ────────────────────────────────────────────────────
    ocr_text = ocr_frame(img)
    matched  = match_plate(ocr_text, lecturers) if ocr_text else None
    plate    = matched["plate"] if matched else ocr_text

    # If a registered plate found, flag ALL detected boxes as registered
    # so the frontend can highlight them in green
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
