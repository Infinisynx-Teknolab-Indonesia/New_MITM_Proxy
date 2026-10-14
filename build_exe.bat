@echo off
REM ===== Build Mini MITM Proxy jadi .exe (Windows) =====
REM Jalankan dari folder proyek. Butuh Python 3.10+ dgn tkinter.

echo [1/2] Install PyInstaller...
py -3.12 -m pip install --upgrade pyinstaller

echo [2/2] Build EXE...
py -3.12 -m PyInstaller --noconfirm --onefile --windowed ^
  --name MiniMITMProxy ^
  --add-data "plugins;plugins" ^
  app.py

echo.
echo Selesai. File ada di: dist\MiniMITMProxy.exe
pause
