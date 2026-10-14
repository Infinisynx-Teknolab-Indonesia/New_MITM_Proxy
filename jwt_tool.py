"""Tool JWT sederhana (tanpa dependency luar).

- decode(token)  -> (header_dict, payload_dict, signature_str)
- encode(header, payload, alg, secret) -> token baru
  alg: "none" (tanpa tanda tangan) atau "HS256" (HMAC-SHA256 pakai secret)
- find_in_headers(headers) -> daftar token JWT yang terdeteksi (Authorization/Cookie)
"""
import base64
import hashlib
import hmac
import json
import re

_JWT_RE = re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]*")


def _b64url_decode(s):
    s = s.encode() if isinstance(s, str) else s
    s += b"=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s)


def _b64url_encode(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def decode(token):
    parts = token.strip().split(".")
    if len(parts) < 2:
        raise ValueError("Bukan JWT (minimal header.payload).")
    header = json.loads(_b64url_decode(parts[0]))
    payload = json.loads(_b64url_decode(parts[1]))
    sig = parts[2] if len(parts) > 2 else ""
    return header, payload, sig


def encode(header, payload, alg="none", secret=""):
    header = dict(header)
    header["alg"] = alg
    h = _b64url_encode(json.dumps(header, separators=(",", ":")).encode())
    p = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode())
    signing_input = f"{h}.{p}".encode()
    if alg in ("none", "None"):
        return f"{h}.{p}."
    if alg == "HS256":
        sig = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
        return f"{h}.{p}.{_b64url_encode(sig)}"
    raise ValueError("alg tidak didukung (pakai none / HS256): " + alg)


def verify_hs256(token, secret):
    parts = token.strip().split(".")
    if len(parts) != 3:
        return False
    signing_input = f"{parts[0]}.{parts[1]}".encode()
    expected = _b64url_encode(hmac.new(secret.encode(), signing_input, hashlib.sha256).digest())
    return hmac.compare_digest(expected, parts[2])


def find_in_headers(headers):
    found = []
    for _k, v in headers:
        for m in _JWT_RE.findall(v or ""):
            if m not in found:
                found.append(m)
    return found
