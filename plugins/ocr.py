"""Action plugin: OCR gambar dari response.

Dipanggil manual: HTTP History -> klik-kanan -> Kirim ke Plugin -> OCR.
Membaca teks dari gambar di response body.

Butuh: pip install pillow pytesseract  + install Tesseract OCR
(Windows: https://github.com/UB-Mannheim/tesseract/wiki).
"""
NAME = "OCR Gambar"
DESCRIPTION = "Baca teks dari gambar di response (butuh pillow + pytesseract + Tesseract)"
MENU = "OCR gambar (response)"
REQUIRES = ["pillow", "pytesseract"]   # otomatis di-pip-install saat plugin diaktifkan


def action(ctx):
    body = ctx.res_body
    if not body:
        return "Response body kosong / bukan gambar."
    try:
        import io
        from PIL import Image
        import pytesseract
    except Exception as e:
        return ("Paket belum lengkap.\n"
                "Jalankan: pip install pillow pytesseract\n"
                "lalu install Tesseract OCR (Windows: UB-Mannheim build).\n\n" + str(e))
    try:
        img = Image.open(io.BytesIO(body))
    except Exception as e:
        return "Body ini sepertinya bukan gambar yang valid.\n" + str(e)
    try:
        text = pytesseract.image_to_string(img)
    except Exception as e:
        return ("Gagal menjalankan OCR. Pastikan Tesseract terpasang & ada di PATH.\n"
                "Atau set: pytesseract.pytesseract.tesseract_cmd = r'C:\\Program Files\\Tesseract-OCR\\tesseract.exe'\n\n"
                + str(e))
    return text.strip() or "(tidak ada teks terbaca)"
