"""Sistem plugin gaya Burp.

Tiap plugin = satu file .py di folder plugins/. Contoh isinya:

    NAME = "Tambah header"
    DESCRIPTION = "Menyisipkan header X-Debug ke tiap request"

    def on_request(ctx):
        ctx.set_header("X-Debug", "1")

    def on_response(ctx):
        pass

Objek ctx yang diberikan:
  Request : .method .scheme .host .port .path .headers .body (bytes)
  Response: .status .status_line .headers .body (bytes) + .req (info request)
Method bantu: ctx.get_header(k) / ctx.set_header(k,v) / ctx.remove_header(k)
             ctx.text (body sebagai str, bisa di-set) ; ctx.drop() untuk blokir.

Plugin dijalankan OTOMATIS sebelum intercept manual. Jadi plugin bisa
dipakai untuk "buka blokir" (hapus header pemblokir, timpa response 403), dsb.
"""
import importlib
import importlib.util
import os
import subprocess
import sys
import traceback

import config

# nama pip -> nama import (untuk cek apakah sudah terpasang)
_PIP_IMPORT = {
    "pillow": "PIL",
    "beautifulsoup4": "bs4",
    "pyyaml": "yaml",
    "opencv-python": "cv2",
}


def _missing(reqs):
    miss = []
    for r in reqs:
        mod = _PIP_IMPORT.get(r.lower(), r.replace("-", "_").split("==")[0])
        try:
            importlib.import_module(mod)
        except Exception:
            miss.append(r)
    return miss


def ensure_requirements(plugin, log=lambda s: None):
    """Install dependensi (REQUIRES) plugin via pip kalau belum ada.
    Return (ok, pesan)."""
    reqs = list(getattr(plugin.module, "REQUIRES", []) or []) if plugin.module else []
    if not reqs:
        return True, "tidak ada dependensi"
    miss = _missing(reqs)
    if not miss:
        return True, "dependensi sudah lengkap"
    log("Menginstall via pip: " + ", ".join(miss) + "\n")
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", *miss],
            capture_output=True, text=True)
        if proc.stdout:
            log(proc.stdout[-3000:])
        if proc.returncode != 0:
            log("\n" + (proc.stderr[-2000:] or ""))
            return False, "pip gagal (kode %d)" % proc.returncode
        return True, "berhasil"
    except Exception as e:
        return False, str(e)

from paths import BASE_DIR
PLUGINS_DIR = os.path.join(BASE_DIR, "plugins")


# ------------------------------ context ------------------------------

class _Ctx:
    def __init__(self, headers, body):
        self.headers = [list(h) for h in headers]   # list of [key, value]
        self.body = body
        self.dropped = False

    # --- helper header (case-insensitive) ---
    def get_header(self, key):
        key = key.lower()
        for k, v in self.headers:
            if k.lower() == key:
                return v
        return None

    def set_header(self, key, value):
        lk = key.lower()
        for h in self.headers:
            if h[0].lower() == lk:
                h[1] = str(value)
                return
        self.headers.append([key, str(value)])

    def remove_header(self, key):
        lk = key.lower()
        self.headers = [h for h in self.headers if h[0].lower() != lk]

    # --- helper body teks ---
    @property
    def text(self):
        try:
            return self.body.decode("utf-8")
        except Exception:
            return ""

    @text.setter
    def text(self, value):
        self.body = value.encode("utf-8")

    def drop(self):
        self.dropped = True


class RequestCtx(_Ctx):
    def __init__(self, fields, headers, body):
        super().__init__(headers, body)
        self.method = fields["method"]
        self.scheme = fields["scheme"]
        self.host = fields["host"]
        self.port = fields["port"]
        self.path = fields["path"]

    def _fields(self):
        return {"method": self.method, "scheme": self.scheme,
                "host": self.host, "port": self.port, "path": self.path}


class ResponseCtx(_Ctx):
    def __init__(self, fields, headers, body, req_info):
        super().__init__(headers, body)
        self.status_line = fields["status_line"]
        self.req = req_info or {}

    @property
    def status(self):
        parts = self.status_line.split(" ")
        try:
            return int(parts[1])
        except (IndexError, ValueError):
            return 0

    @status.setter
    def status(self, code):
        parts = self.status_line.split(" ", 2)
        proto = parts[0] if parts else "HTTP/1.1"
        reason = parts[2] if len(parts) > 2 else ""
        self.status_line = f"{proto} {code} {reason}".rstrip()

    def _fields(self):
        return {"status_line": self.status_line}


# ------------------------------ manager ------------------------------

class ActionCtx:
    """Konteks yang dikirim ke action plugin (mis. OCR)."""
    def __init__(self, entry):
        self.method = entry.get("method", "")
        self.url = entry.get("url", "")
        self.host = entry.get("host", "")
        self.path = entry.get("path", "")
        self.status = entry.get("status", 0)
        self.status_line = entry.get("status_line", "")
        self.req_headers = entry.get("req_headers", [])
        self.res_headers = entry.get("res_headers", [])
        self.req_text = entry.get("req_text", "")
        self.res_text = entry.get("res_text", "")
        self.req_body = entry.get("req_body", b"")     # bytes mentah (sudah di-decompress)
        self.res_body = entry.get("res_body", b"")

    def header(self, headers, key):
        key = key.lower()
        for k, v in headers:
            if k.lower() == key:
                return v
        return None


class Plugin:
    def __init__(self, name, module, filename):
        self.name = name
        self.module = module
        self.filename = filename
        self.description = getattr(module, "DESCRIPTION", "")
        self.menu = getattr(module, "MENU", name) if module else name
        self.has_action = bool(module and hasattr(module, "action"))
        self.error = None


class PluginManager:
    def __init__(self):
        self.plugins = []            # list[Plugin], urut
        os.makedirs(PLUGINS_DIR, exist_ok=True)

    # --- status enable disimpan di settings.json ---
    def _enabled_map(self):
        return (config.get().get("plugins") or {})

    def is_enabled(self, name):
        return bool(self._enabled_map().get(name, False))

    def set_enabled(self, name, value):
        m = dict(self._enabled_map())
        m[name] = bool(value)
        config.update({"plugins": m})

    # --- load / reload ---
    def load_all(self):
        self.plugins = []
        for fn in sorted(os.listdir(PLUGINS_DIR)):
            if not fn.endswith(".py") or fn.startswith("_"):
                continue
            path = os.path.join(PLUGINS_DIR, fn)
            try:
                spec = importlib.util.spec_from_file_location(f"plugin_{fn[:-3]}", path)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                name = getattr(mod, "NAME", fn[:-3])
                self.plugins.append(Plugin(name, mod, fn))
            except Exception:
                p = Plugin(fn[:-3], None, fn)
                p.error = traceback.format_exc(limit=3)
                self.plugins.append(p)

    def import_file(self, src_path):
        """Salin file .py ke folder plugins lalu reload. Return (ok, pesan)."""
        if not src_path.endswith(".py"):
            return False, "File harus .py"
        base = os.path.basename(src_path)
        dst = os.path.join(PLUGINS_DIR, base)
        try:
            with open(src_path, "r", encoding="utf-8") as f:
                code = f.read()
            with open(dst, "w", encoding="utf-8") as f:
                f.write(code)
        except Exception as e:
            return False, str(e)
        self.load_all()
        return True, f"Plugin '{base}' diimport"

    # --- eksekusi ---
    def _run(self, hook, ctx):
        for p in self.plugins:
            if p.module is None or not self.is_enabled(p.name):
                continue
            fn = getattr(p.module, hook, None)
            if not fn:
                continue
            try:
                fn(ctx)
            except Exception:
                p.error = traceback.format_exc(limit=3)
            if ctx.dropped:
                break
        return ctx

    def apply_request(self, fields, headers, body):
        ctx = self._run("on_request", RequestCtx(fields, headers, body))
        if ctx.dropped:
            return None
        return ctx._fields(), [tuple(h) for h in ctx.headers], ctx.body

    def apply_response(self, fields, headers, body, req_info=None):
        ctx = self._run("on_response", ResponseCtx(fields, headers, body, req_info))
        if ctx.dropped:
            return None
        return ctx._fields(), [tuple(h) for h in ctx.headers], ctx.body

    # --- action plugins (dipanggil manual dari request/response) ---
    def action_plugins(self):
        return [p for p in self.plugins if p.has_action and self.is_enabled(p.name)]

    def run_action(self, plugin, entry):
        """Jalankan plugin.action(ctx). Kembalikan teks hasil."""
        try:
            return str(plugin.module.action(ActionCtx(entry)))
        except Exception:
            import traceback
            return "Plugin error:\n" + traceback.format_exc(limit=4)


manager = PluginManager()
