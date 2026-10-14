"""Catatan lalu-lintas (HTTP history) ala Burp.

Setiap transaksi request+response lengkap disimpan di sini, TERLEPAS dari
apakah intercept sedang menahan atau tidak. UI menampilkannya di tab History;
tiap baris bisa diklik untuk melihat request yang dikirim dan response-nya.
"""
import itertools
import threading
import time

from interceptor import _decode, decompress   # (teks, editable) + dekompresi gzip/br/zstd
import ua as _ua

_lock = threading.Lock()
_log = []                 # terbaru di depan
_ids = itertools.count(1)
MAX = 1000


def _status_code(status_line):
    try:
        return int(status_line.split(" ")[1])
    except (IndexError, ValueError):
        return 0


def record(req, res):
    """Simpan satu transaksi lengkap.
    req: {method,scheme,host,port,path,headers,body}
    res: {status_line,headers,body}
    """
    rq_body, _ = decompress(req["headers"], req["body"])
    rs_body, _ = decompress(res["headers"], res["body"])
    req_text, _ = _decode(req["headers"], rq_body)
    res_text, _ = _decode(res["headers"], rs_body)
    # batasi penyimpanan body mentah (untuk action plugin spt OCR) agar hemat memori
    CAP = 4 * 1024 * 1024
    rq_raw = rq_body[:CAP]
    rs_raw = rs_body[:CAP]
    user_agent = ""
    for k, v in req["headers"]:
        if k.lower() == "user-agent":
            user_agent = v
            break
    platform, browser = _ua.classify(user_agent)
    entry = {
        "id": next(_ids),
        "ts": time.time(),
        "method": req["method"],
        "scheme": req["scheme"],
        "host": req["host"],
        "port": req["port"],
        "path": req["path"],
        "url": f'{req["scheme"]}://{req["host"]}{req["path"]}',
        "req_headers": [list(h) for h in req["headers"]],
        "req_text": req_text,
        "req_body": rq_raw,
        "req_len": len(req["body"]),
        "status_line": res["status_line"],
        "status": _status_code(res["status_line"]),
        "res_headers": [list(h) for h in res["headers"]],
        "res_text": res_text,
        "res_body": rs_raw,
        "res_len": len(res["body"]),
        "platform": platform,
        "browser": browser,
    }
    with _lock:
        _log.insert(0, entry)
        del _log[MAX:]


def snapshot(limit=500):
    """Ringkasan untuk tabel (tanpa body besar)."""
    with _lock:
        out = []
        for e in _log[:limit]:
            out.append({k: e[k] for k in
                        ("id", "ts", "method", "host", "path", "status", "res_len",
                         "scheme", "platform", "browser")})
        return out


def aggregate():
    """Hitung jumlah per platform -> browser untuk sidebar.
    Kembalikan {platform: {"_count": n, browser: n}}."""
    with _lock:
        tree = {}
        for e in _log:
            plat = e.get("platform", "Lainnya")
            brow = e.get("browser", "Lainnya")
            node = tree.setdefault(plat, {"_count": 0})
            node["_count"] += 1
            node[brow] = node.get(brow, 0) + 1
        return tree


def get(entry_id):
    """Detail lengkap satu transaksi (untuk panel request/response)."""
    with _lock:
        for e in _log:
            if e["id"] == entry_id:
                return dict(e)
    return None


def clear():
    with _lock:
        _log.clear()
