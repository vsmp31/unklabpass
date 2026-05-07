# 🧪 Hybrid Approach - Testing Guide

## Test Scenarios

### ✅ Scenario 1: Auto OCR Success (Registered Plate)
**Steps:**
1. Start camera
2. Point at registered vehicle (e.g., DB1482WD)
3. Wait for YOLO detection (green box appears)

**Expected Result:**
- Auto OCR runs immediately (1-2 seconds)
- Info card shows:
  - ✓ Terdaftar badge (green)
  - Cropped plate image
  - Plate number: DB1482WD
  - Owner name
  - **"Re-scan" button** (blue)
- Terminal log: `✅ Plat DB1482WD — [Owner Name]`
- YOLO box shows: `✔ DB1482WD`

---

### ✅ Scenario 2: Auto OCR Success (Unregistered Plate)
**Steps:**
1. Start camera
2. Point at unregistered vehicle (e.g., DB9999XX)
3. Wait for YOLO detection

**Expected Result:**
- Auto OCR runs immediately
- Info card shows:
  - ❌ TIDAK TERDAFTAR badge (red)
  - Cropped plate image (red border)
  - Plate number: DB9999XX
  - Owner: TIDAK TERDAFTAR
  - **"Re-scan" button** (blue)
- Terminal log: `❌ Plat DB9999XX — TIDAK TERDAFTAR`
- YOLO box shows: `DB9999XX`

---

### ✅ Scenario 3: Re-scan Correction (Wrong OCR)
**Steps:**
1. Auto OCR detects wrong plate (e.g., reads "DB148ZWD" instead of "DB1482WD")
2. Click **"Re-scan"** button

**Expected Result:**
- Loading spinner appears
- Terminal log: `[Re-scan] Memproses ulang OCR dari cropped image...`
- After 1-2 seconds:
  - Corrected plate appears: DB1482WD
  - Info card updates with correct owner
  - Terminal log: `✅ [Re-scan] Plat DB1482WD — [Owner Name]`
  - Database log created with corrected plate

---

### ✅ Scenario 4: Re-scan on Failed OCR
**Steps:**
1. Auto OCR fails (no text detected)
2. Info card shows: ⚠ OCR Kosong
3. Click **"Coba Lagi"** button

**Expected Result:**
- Loading spinner appears
- Re-scan attempts OCR again
- If successful: Shows plate and owner
- If failed again: Shows "Coba Lagi" button again
- Terminal log: `[Re-scan] OCR GAGAL: Raw OCR: "..."` or success message

---

### ✅ Scenario 5: Multiple Re-scans
**Steps:**
1. Auto OCR completes (any result)
2. Click "Re-scan" button
3. Wait for result
4. Click "Re-scan" button again
5. Repeat 2-3 times

**Expected Result:**
- Each re-scan works independently
- Loading spinner shows each time
- Results update correctly
- Terminal shows multiple `[Re-scan]` logs
- No errors or freezing

---

### ✅ Scenario 6: Re-scan Uses Same Image (No Re-capture)
**Steps:**
1. Auto OCR detects plate
2. Move camera away from vehicle (point at wall)
3. Click "Re-scan" button

**Expected Result:**
- Re-scan still works (uses cached b64_crop)
- Same plate image is processed
- No new capture from video stream
- Result appears even though camera is not pointing at vehicle

---

## 🔍 Debug Checklist

### Frontend Console (F12)
```javascript
// Check if rescanOCR function exists
typeof rescanOCR === 'function'  // Should be true

// Check if b64_crop is passed correctly
// Look for: onclick="rescanOCR('data:image/jpeg;base64,...')"
```

### Terminal Logs
```
[INFO] [OCR RAW] "DB 1482 WD" → Cleaned: "DB1482WD"
[TERDAFTAR] ✅ Plat DB1482WD — John Doe
[INFO] [Re-scan] Memproses ulang OCR dari cropped image...
[INFO] [Re-scan OCR] "DB 1482 WD" → Cleaned: "DB1482WD"
[TERDAFTAR] ✅ [Re-scan] Plat DB1482WD — John Doe
```

### Network Tab (F12)
```
POST /ocr_only
Request Payload:
{
  "image": "data:image/jpeg;base64,...",
  "save_log": false  // Auto OCR
}

POST /ocr_only
Request Payload:
{
  "image": "data:image/jpeg;base64,...",
  "save_log": true   // Re-scan
}
```

---

## 🐛 Common Issues & Solutions

### Issue 1: Re-scan button not appearing
**Cause:** Button HTML not in updateInfoCard functions
**Solution:** Check lines ~531, ~545, ~622 in home.html

### Issue 2: Re-scan does nothing
**Cause:** rescanOCR function not defined
**Solution:** Check line ~555 in home.html

### Issue 3: Re-scan captures new image
**Cause:** Passing wrong parameter to rescanOCR
**Solution:** Ensure `onclick="rescanOCR('${b64_crop}')"` uses template literal

### Issue 4: Loading spinner doesn't show
**Cause:** captureBox.innerHTML not updated
**Solution:** Check line ~558 in home.html

### Issue 5: Re-scan creates duplicate logs
**Cause:** save_log parameter always true
**Solution:** Auto OCR uses `save_log: false`, Re-scan uses `save_log: true`

---

## 📊 Performance Metrics

### Expected Timings:
- **Auto OCR**: 1-2 seconds (from YOLO detection to result)
- **Re-scan**: 1-2 seconds (same as auto OCR)
- **YOLO Detection**: 30-50ms per frame (30 FPS)
- **Total (Detection → Result)**: 2-3 seconds

### Optimization Points:
- ✅ Only 2 preprocessing variants (was 5)
- ✅ 600px resize (was 800px)
- ✅ Fast denoise (h=7, template=5, search=15)
- ✅ No voting system (instant results)
- ✅ 70% confidence threshold (balance speed/accuracy)

---

## ✅ Acceptance Criteria

- [ ] Auto OCR triggers at 70% confidence
- [ ] Re-scan button visible on all results
- [ ] Re-scan uses cached image (no re-capture)
- [ ] Loading spinner shows during re-scan
- [ ] Terminal logs show [Re-scan] prefix
- [ ] Database logs re-scan results
- [ ] Button hover effects work
- [ ] Multiple re-scans work correctly
- [ ] No JavaScript errors in console
- [ ] No Python errors in Flask logs

---

## 🎯 Success Criteria

**The hybrid approach is successful if:**
1. ⚡ Auto OCR provides results in 1-2 seconds
2. 🎯 Re-scan allows manual correction
3. 🚀 No performance degradation
4. 🐛 No errors or crashes
5. 👍 User-friendly and intuitive

---

## 📝 Test Report Template

```
Date: ___________
Tester: ___________

Scenario 1 (Auto OCR Registered): ☐ Pass ☐ Fail
Scenario 2 (Auto OCR Unregistered): ☐ Pass ☐ Fail
Scenario 3 (Re-scan Correction): ☐ Pass ☐ Fail
Scenario 4 (Re-scan Failed OCR): ☐ Pass ☐ Fail
Scenario 5 (Multiple Re-scans): ☐ Pass ☐ Fail
Scenario 6 (No Re-capture): ☐ Pass ☐ Fail

Notes:
_________________________________
_________________________________
_________________________________

Overall Status: ☐ Ready ☐ Needs Fix
```
