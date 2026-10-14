"""Antrian flow yang dicegat + status intercept.

Thread proxy akan BLOK di fungsi intercept() sampai user menekan Forward/Drop
(saat intercept untuk arah itu ON). Di sinilah request & response bisa diubah.

Body yang terkompresi (gzip/deflate/br/zstd) otomatis di-decompress untuk
ditampilkan & diedit; header Content-Encoding dibuang supaya hasil edit tetap valid.
"""
import gzip
import itertools
import threading
import time
import zlib

try:
    import brotli  # opsional (pip install brotli) untuk Content-Encoding: br
except Exception:
    brotli = None
try:
    import zstandard as _zstd  # opsional (pip install zstandard) untuk zstd
except Exception:
    _zstd = None

_lock = threading.Lock()
_pending = {}
_history = []
_ids = itertools.count(1)

# Default OFF (seperti Burp): trafik lewat & tercatat di History tanpa menahan.
enabled = {"request": False, "response": False}


def _content_encoding(headers):
    for k, v in headers:
        if k.lower() == "content-encoding":
            return (v or "").lower().strip()
    return ""


def decompress(headers, body):
    """Kembalikan (body_terdekompresi, True) bila berhasil, atau (body_asli, False)."""
    enc = _content_encoding(headers)
    if not enc or not body:
        return body, False
    try:
        if enc == "gzip":
            return gzip.decompress(body), True
        if enc == "deflate":
            try:
                return zlib.decompress(body), True
            except zlib.error:
                return zlib.decompress(body, -zlib.MAX_WBITS), True
        if enc == "br" and brotli:
            return brotli.decompress(body), True
        if enc == "zstd" and _zstd:
            return _zstd.ZstdDecompressor().decompress(body), True
    except Exception:
        return body, False
    return body, False


def _decode(headers, body):
    """(teks, editable). utf-8 -> editable; kalau gagal tampilkan apa adanya (latin1, read-only)."""
    if not body:
        return "", True
    try:
        return body.decode("utf-8"), True
    except UnicodeDecodeError:
        return body.decode("latin1"), False


class Flow:
    def __init__(self, kind, fields, headers, body, request=None):
        self.id = next(_ids)
        self.kind = kind
        self.fields = dict(fields)
        self.request = request          # untuk response: info request asal
        hdrs = [list(h) for h in headers]
        dec_body, decomp = decompress(headers, body)
        if decomp:
            hdrs = [h for h in hdrs if h[0].lower() != "content-encoding"]
            body = dec_body
        self.headers = hdrs
        self.body = body
        self.body_text, self.editable = _decode(self.headers, body)
        self.event = threading.Event()
        self.action = "forward"
        self.ts = time.time()

    def to_json(self):
        d = {"id": self.id, "kind": self.kind, "ts": self.ts,
             "headers": self.headers, "body_text": self.body_text,
             "body_editable": self.editable, "body_len": len(self.body),
             "request": self.request}
        d.update(self.fields)
        return d


def _summary(flow):
    f = flow.fields
    if flow.kind == "request":
        return f"{f.get('method')} {f.get('scheme')}://{f.get('host')}{f.get('path')}"
    return f.get("status_line", "")


def _log(kind, summary, action):
    with _lock:
        _history.insert(0, {"kind": kind, "summary": summary, "action": action, "ts": time.time()})
        del _history[200:]


def intercept(kind, fields, headers, body, request=None):
    flow = Flow(kind, fields, headers, body, request=request)
    if not enabled.get(kind):
        _log(kind, _summary(flow), "pass")
        # tetap kembalikan body hasil decompress + header tanpa content-encoding
        return flow.fields, [tuple(h) for h in flow.headers], flow.body

    with _lock:
        _pending[flow.id] = flow
    flow.event.wait()
    with _lock:
        _pending.pop(flow.id, None)

    if flow.action == "drop":
        _log(kind, _summary(flow), "drop")
        return None
    _log(kind, _summary(flow), "forward")
    return flow.fields, [tuple(h) for h in flow.headers], flow.body


def intercept_request(fields, headers, body):
    return intercept("request", fields, headers, body)


def intercept_response(fields, headers, body, request=None):
    return intercept("response", fields, headers, body, request=request)


def snapshot():
    with _lock:
        return {
            "enabled": dict(enabled),
            "pending": [f.to_json() for f in _pending.values()],
            "history": list(_history[:40]),
        }


def set_enabled(kind, value):
    if kind in enabled:
        enabled[kind] = bool(value)


def resolve(flow_id, action, fields=None, headers=None, body_text=None):
    with _lock:
        flow = _pending.get(flow_id)
    if not flow:
        return False
    flow.action = action
    if action == "forward":
        if fields:
            flow.fields.update(fields)
        if headers is not None:
            flow.headers = headers
        if body_text is not None and flow.editable:
            flow.body = body_text.encode("utf-8")
    flow.event.set()
    return True


def resolve_all():
    with _lock:
        flows = list(_pending.values())
    for f in flows:
        f.event.set()
