"""Deteksi platform & browser/aplikasi dari header User-Agent.

Dipakai sidebar untuk mengelompokkan trafik: tahu app-mu diakses dari
Windows/Android/iOS, lewat browser apa atau dari aplikasi.
"""


def classify(ua):
    u = ua or ""
    ul = u.lower()

    if "windows" in ul:
        plat = "Windows"
    elif "iphone" in ul or "ipad" in ul or "ios" in ul or "cfnetwork" in ul:
        plat = "iOS"
    elif "android" in ul:
        plat = "Android"
    elif "mac os" in ul or "macintosh" in ul:
        plat = "macOS"
    elif "linux" in ul:
        plat = "Linux"
    else:
        plat = "Lainnya"

    if "edg" in ul:
        brow = "Edge"
    elif "opr" in ul or "opera" in ul:
        brow = "Opera"
    elif "samsungbrowser" in ul:
        brow = "Samsung Internet"
    elif "firefox" in ul or "fxios" in ul:
        brow = "Firefox"
    elif "crios" in ul:
        brow = "Chrome"
    elif "chrome" in ul:
        brow = "Chrome"
    elif "safari" in ul:
        brow = "Safari"
    elif "dart" in ul or "flutter" in ul:
        brow = "Flutter/Dart (app)"
    elif "okhttp" in ul:
        brow = "okhttp (app)"
    elif "cfnetwork" in ul or "darwin" in ul:
        brow = "App iOS"
    elif "curl" in ul:
        brow = "curl"
    elif "python" in ul or "urllib" in ul or "requests" in ul:
        brow = "python"
    elif u.strip() == "":
        brow = "(tanpa UA)"
    else:
        brow = "Lainnya"

    return plat, brow
