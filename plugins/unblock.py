"""Plugin: Buka Blokir (Unblock).

Meniru fitur Burp untuk melewati pemblokiran sisi server/klien:
- Hapus header response yang sering memblokir tampilan (CSP, X-Frame-Options, dll).
- Kalau server membalas 403/451 (Forbidden / Unavailable For Legal Reasons),
  ubah jadi 200 OK supaya tidak dianggap diblokir.
- Hapus header CORS ketat lalu izinkan semua origin.

Matikan kalau tidak perlu — ini mengubah response apa adanya.
"""
NAME = "Buka Blokir (Unblock)"
DESCRIPTION = "Hapus header pemblokir (CSP/CORS/frame) & ubah 403/451 -> 200"

_BLOCK_HEADERS = [
    "content-security-policy",
    "content-security-policy-report-only",
    "x-frame-options",
    "cross-origin-opener-policy",
    "cross-origin-embedder-policy",
    "strict-transport-security",
]


def on_response(ctx):
    for h in _BLOCK_HEADERS:
        ctx.remove_header(h)

    # izinkan CORS
    ctx.set_header("Access-Control-Allow-Origin", "*")
    ctx.set_header("Access-Control-Allow-Headers", "*")
    ctx.set_header("Access-Control-Allow-Methods", "*")

    # anggap halaman "terblokir" sebagai sukses
    if ctx.status in (403, 451):
        ctx.status = 200
