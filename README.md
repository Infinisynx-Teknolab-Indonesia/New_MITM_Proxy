# Mini MITM Proxy

Intercepting proxy (seperti **mitmproxy / Burp Suite**) buatan sendiri dengan Python + Tkinter.
Mencegat, melihat & mengedit request/response HTTP/HTTPS, dengan Repeater, Intruder, JWT,
plugin, cookie jar, browser bawaan, dan integrasi AI lokal.

> ⚠️ **Hanya untuk perangkat & trafik milikmu sendiri** (pengujian aplikasi sendiri, belajar
> keamanan). Jangan dipakai untuk menyadap orang lain.

## ✨ Fitur
- **Intercept** dua arah: tahan, edit, Forward/Drop request & response.
- **HTTP History**: semua trafik tercatat, klik untuk lihat request + response, ada Find.
- **Repeater** multi-tab: kirim ulang request, Duplikat tab.
- **Intruder** multi-tab (mode Sniper dengan `{PAYLOAD}`).
- **JWT**: decode/edit/re-sign (HS256 / none), kirim token ke Repeater.
- **Plugins**: file `.py` drop-in (auto / action seperti OCR); dependensi pip auto-install.
- **Sidebar klien**: kelompokkan trafik per platform & browser (dari User-Agent).
- **Upstream proxy**, **Invisible/transparent proxy**, **Cookie jar (session)**.
- **🌐 Browser**: buka Chrome/Edge/Brave yang terarah ke proxy, tiap sesi terpisah.
- **AI**: jelaskan request/response & **AI Runner** (AI menyusun lalu menjalankan request)
  lewat endpoint OpenAI-compatible / Ollama lokal.
- **Multi-bahasa**: Indonesia / English / 中文.

## 🚀 Instalasi & Jalankan
Butuh **Python 3.10+** dengan **Tcl/Tk (tkinter)**. (Installer python.org centang "tcl/tk and IDLE".)

```bash
git clone https://github.com/<username>/mini-mitm-proxy.git
cd mini-mitm-proxy
pip install -r requirements.txt
python app.py
```

Windows (kalau `python` salah versi):
```bat
py -3.12 -m pip install -r requirements.txt
py -3.12 app.py
```

## 🔌 Pakai
1. Klik **Start** (proxy di `127.0.0.1:8080`).
2. Arahkan browser/HP ke proxy itu, **atau** klik **🌐 Browser** (otomatis lewat proxy,
   tak perlu install sertifikat).
3. Untuk HTTPS dari browser biasa: install `ca/ca.crt` sebagai *Trusted Root CA*
   (menu **Tools → Export ca.crt**).
4. Lihat trafik di **HTTP History**; kirim ke **Repeater/Intruder/JWT** lewat klik-kanan.

### Intercept aplikasi Flutter (milik sendiri)
Flutter tidak ikut proxy device. Sertakan `flutter_proxy.dart` di `lib/` lalu panggil di `main()`:
```dart
import 'flutter_proxy.dart';
void main() { enableDebugProxy('192.168.1.5', 8080); runApp(const MyApp()); }
```

### AI (opsional)
Settings → **AI**: isi endpoint (OpenAI-compatible `…/v1/chat/completions` atau Ollama `…/api/chat`),
Muat Model, pilih model. Lalu tombol **🤖 Jelaskan dgn AI** / tab **AI Runner**.

## 🧩 Bikin Plugin
Taruh file `.py` di `plugins/` (atau Settings → Plugins → Install):
```python
NAME = "Contoh"
DESCRIPTION = "..."
# REQUIRES = ["pillow"]   # opsional, auto pip install

def on_request(ctx):      # otomatis tiap request
    ctx.set_header("X-Debug", "1")

def on_response(ctx):     # otomatis tiap response
    if ctx.status == 403:
        ctx.status = 200

def action(ctx):          # "action": dipanggil manual dari HTTP History
    return "hasil teks"
```

## 📦 Dependensi
- Wajib: `cryptography`
- Opsional: `brotli`, `zstandard` (lihat body br/zstd), `flask` (dashboard web),
  `pillow` + `pytesseract` (+ Tesseract OCR) untuk plugin OCR.

## ⚠️ Batasan
Belum mendukung HTTP/2 & WebSocket. Untuk REST/JSON sudah cukup.

## 📄 Lisensi
MIT — lihat [LICENSE](LICENSE).
