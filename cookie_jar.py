"""Cookie jar sederhana (session) ala Burp.

- capture(host, response_headers): simpan cookie dari Set-Cookie.
- apply(host, request_headers): sisipkan cookie tersimpan ke request (yang sudah
  ada di request tetap diprioritaskan).
- Cocok dipakai dengan Repeater supaya session tetap jalan tanpa salin-tempel cookie.
"""
import threading

_lock = threading.Lock()
_jar = {}      # host -> {name: value}


def _domain_key(host):
    return (host or "").lower().lstrip(".")


def capture(host, headers):
    key = _domain_key(host)
    with _lock:
        store = _jar.setdefault(key, {})
        for k, v in headers:
            if k.lower() != "set-cookie":
                continue
            first = v.split(";", 1)[0].strip()
            if "=" in first:
                name, _, val = first.partition("=")
                name = name.strip()
                if name:
                    store[name] = val.strip()


def apply(host, headers):
    """Kembalikan headers dengan Cookie jar tersisipkan (cookie di request menang)."""
    key = _domain_key(host)
    with _lock:
        jar = dict(_jar.get(key, {}))
    if not jar:
        return headers

    # cookie yang sudah ada di request
    existing = {}
    cookie_idx = None
    out = []
    for i, (k, v) in enumerate(headers):
        if k.lower() == "cookie":
            cookie_idx = len(out)
            for part in v.split(";"):
                part = part.strip()
                if "=" in part:
                    n, _, val = part.partition("=")
                    existing[n.strip()] = val.strip()
            out.append([k, v])
        else:
            out.append([k, v])

    merged = dict(jar)
    merged.update(existing)   # request menang
    cookie_str = "; ".join(f"{n}={val}" for n, val in merged.items())
    if cookie_idx is not None:
        out[cookie_idx][1] = cookie_str
    else:
        out.append(["Cookie", cookie_str])
    return [tuple(h) for h in out]


def snapshot():
    with _lock:
        return {h: dict(c) for h, c in _jar.items()}


def clear():
    with _lock:
        _jar.clear()
