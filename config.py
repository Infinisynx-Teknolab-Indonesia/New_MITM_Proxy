"""Pengaturan aplikasi, disimpan ke settings.json (di folder yang sama)."""
import json
import os
import threading

_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.json")
_lock = threading.Lock()

_DEFAULT = {
    "listen_host": "127.0.0.1",
    "listen_port": 8080,
    "upstream": {                 # teruskan ke proxy lain (gateway)
        "enabled": False,
        "host": "",
        "port": 8081,
        "user": "",
        "password": "",
    },
    "plugins": {},                # {nama_plugin: True/False}  -> status aktif
    "invisible": False,           # invisible/transparent proxy (klien tanpa setting proxy)
    "cookie_jar": False,          # simpan cookie dari response & ikutkan ke request (session)
    "ai": {                       # koneksi ke AI lokal (Prakash AI dll)
        "kind": "openai",         # "openai" (OpenAI-compatible) atau "ollama"
        "url": "http://127.0.0.1:1234/v1/chat/completions",
        "model": "",
        "api_key": "",
    },
}

_cfg = None


def _deep_default(data):
    out = {
        "listen_host": data.get("listen_host", _DEFAULT["listen_host"]),
        "listen_port": int(data.get("listen_port", _DEFAULT["listen_port"])),
    }
    up = dict(_DEFAULT["upstream"])
    up.update(data.get("upstream", {}))
    out["upstream"] = up
    out["plugins"] = dict(data.get("plugins", {}))
    out["invisible"] = bool(data.get("invisible", False))
    out["cookie_jar"] = bool(data.get("cookie_jar", False))
    out["lang"] = data.get("lang", "id")
    ai = dict(_DEFAULT["ai"])
    ai.update(data.get("ai", {}))
    out["ai"] = ai
    return out


def _load():
    global _cfg
    data = {}
    if os.path.exists(_PATH):
        try:
            with open(_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}
    _cfg = _deep_default(data)


def get():
    """Kembalikan salinan setting (aman diubah pemanggil)."""
    with _lock:
        if _cfg is None:
            _load()
        return json.loads(json.dumps(_cfg))


def update(new):
    """Timpa sebagian setting lalu simpan ke disk. Kembalikan setting terbaru."""
    with _lock:
        global _cfg
        if _cfg is None:
            _load()
        if "listen_host" in new:
            _cfg["listen_host"] = new["listen_host"]
        if "listen_port" in new:
            _cfg["listen_port"] = int(new["listen_port"])
        if "upstream" in new:
            up = dict(_DEFAULT["upstream"])
            up.update(_cfg.get("upstream", {}))
            up.update(new["upstream"])
            up["port"] = int(up.get("port") or 0)
            _cfg["upstream"] = up
        if "plugins" in new:
            _cfg["plugins"] = dict(new["plugins"])
        if "invisible" in new:
            _cfg["invisible"] = bool(new["invisible"])
        if "cookie_jar" in new:
            _cfg["cookie_jar"] = bool(new["cookie_jar"])
        if "lang" in new:
            _cfg["lang"] = new["lang"]
        if "ai" in new:
            ai = dict(_DEFAULT["ai"])
            ai.update(_cfg.get("ai", {}))
            ai.update(new["ai"])
            _cfg["ai"] = ai
        with open(_PATH, "w", encoding="utf-8") as f:
            json.dump(_cfg, f, indent=2)
        return json.loads(json.dumps(_cfg))
