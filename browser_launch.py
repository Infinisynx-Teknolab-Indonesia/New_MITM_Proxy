"""Luncurkan browser (Chromium-based) yang diarahkan ke proxy, tiap sesi terpisah.

Memakai browser eksternal (Chrome/Edge/Brave) dengan flag:
- --proxy-server       : semua trafik lewat Mini MITM Proxy
- --user-data-dir      : profil terpisah -> SESSION sendiri tiap jendela
- --ignore-certificate-errors : tidak perlu install CA
Trafik otomatis muncul di HTTP History.
"""
import os
import shutil
import subprocess
import tempfile

_WIN_CANDIDATES = [
    (r"C:\Program Files\Google\Chrome\Application\chrome.exe", "Chrome"),
    (r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe", "Chrome"),
    (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", "Edge"),
    (r"C:\Program Files\Microsoft\Edge\Application\msedge.exe", "Edge"),
    (r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe", "Brave"),
]

_sessions = []   # [{"name","proc","profile","label"}]


def find_browsers():
    """Kembalikan {label: path} browser Chromium yang terpasang."""
    found = {}
    for exe, label in [("chrome", "Chrome"), ("google-chrome", "Chrome"),
                       ("chromium", "Chromium"), ("chromium-browser", "Chromium"),
                       ("msedge", "Edge"), ("microsoft-edge", "Edge"),
                       ("brave", "Brave"), ("brave-browser", "Brave")]:
        p = shutil.which(exe)
        if p:
            found.setdefault(label, p)
    for path, label in _WIN_CANDIDATES:
        if os.path.exists(path):
            found.setdefault(label, path)
    return found


def launch(exe, host, port, name):
    """Buka satu jendela browser dengan sesi terpisah menuju proxy."""
    profile = tempfile.mkdtemp(prefix="mitm_sess_")
    args = [
        exe,
        f"--proxy-server=http://{host}:{port}",
        f"--user-data-dir={profile}",
        "--proxy-bypass-list=<-loopback>",   # loopback juga lewat proxy (buat app lokal)
        "--ignore-certificate-errors",
        "--no-first-run",
        "--no-default-browser-check",
        "--new-window",
        "about:blank",
    ]
    try:
        proc = subprocess.Popen(args)
    except Exception as e:
        raise RuntimeError(str(e))
    s = {"name": name, "proc": proc, "profile": profile, "exe": exe}
    _sessions.append(s)
    return s


def sessions():
    """Daftar sesi yang masih hidup (bersihkan yang sudah ditutup)."""
    alive = []
    for s in _sessions:
        if s["proc"].poll() is None:
            alive.append(s)
    _sessions[:] = alive
    return list(_sessions)


def close(session):
    try:
        session["proc"].terminate()
    except Exception:
        pass
    if session in _sessions:
        _sessions.remove(session)
    try:
        shutil.rmtree(session.get("profile", ""), ignore_errors=True)
    except Exception:
        pass
