# 🔧 Fix: Camera Button Error

## 🐛 Masalah

**Error:** Tombol "Start Camera" tidak bisa diklik  
**Penyebab:** Duplikasi kode JavaScript di `templates/home.html`

```javascript
// DUPLIKASI - Line 417-421
if (shouldDisplay && finalPlate !== lastPlate) {
    lastPlate = finalPlate;
    
    if (data.registered) {
if (shouldDisplay && finalPlate !== lastPlate) {  // ❌ DUPLIKAT!
    lastPlate = finalPlate;
```

**Dampak:**
- JavaScript syntax error
- Event listener tidak terpasang
- Tombol camera tidak bisa diklik

---

## ✅ Solusi

Hapus duplikasi kode di line 417-421.

**Sebelum:**
```javascript
if (shouldDisplay && finalPlate !== lastPlate) {
    lastPlate = finalPlate;
    
    if (data.registered) {
if (shouldDisplay && finalPlate !== lastPlate) {  // ❌ DUPLIKAT
    lastPlate = finalPlate;
    
    if (data.registered) {
        // ... code ...
    }
}
```

**Sesudah:**
```javascript
if (shouldDisplay && finalPlate !== lastPlate) {
    lastPlate = finalPlate;
    
    if (data.registered) {
        // ... code ...
    } else {
        // ... code ...
    }
}
```

---

## 🔍 Cara Verifikasi

### 1. Check Console Browser (F12)
**Sebelum fix:**
```
Uncaught SyntaxError: Unexpected token 'if'
```

**Setelah fix:**
```
[INFO] YOLO.onnx loaded at startup.
[DB] Database loaded to cache: vehicles.db
```

### 2. Test Camera Button
1. Refresh page (Ctrl+R)
2. Klik "Start Camera"
3. ✅ Camera harus menyala

---

## 📝 Root Cause

Duplikasi terjadi karena:
1. Copy-paste code saat menambahkan voting system
2. Tidak menghapus code lama
3. Tidak test setelah perubahan

---

## ✅ Prevention

Untuk mencegah error serupa:
1. ✅ Test setelah setiap perubahan
2. ✅ Check console browser (F12) untuk error
3. ✅ Gunakan linter/formatter (ESLint, Prettier)
4. ✅ Code review sebelum commit

---

## 🚀 Status

✅ **FIXED**  
Camera button sekarang berfungsi normal!

---

**Date:** 7 Mei 2026  
**Fixed by:** Code cleanup - removed duplicate if statement
