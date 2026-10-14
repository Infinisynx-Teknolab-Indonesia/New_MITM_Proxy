"""Penentu folder dasar — bekerja baik saat dijalankan sebagai script maupun
sebagai .exe hasil PyInstaller.

- BASE_DIR     : tempat menyimpan data yang bisa ditulis (ca/, settings.json, plugins/).
                 Saat .exe: folder tempat .exe berada. Saat script: folder proyek.
- RESOURCE_DIR : tempat file bawaan yang dibundel (read-only). Saat .exe onefile:
                 folder sementara _MEIPASS. Saat script: sama dengan BASE_DIR.
"""
import os
import sys

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
    RESOURCE_DIR = getattr(sys, "_MEIPASS", BASE_DIR)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    RESOURCE_DIR = BASE_DIR
