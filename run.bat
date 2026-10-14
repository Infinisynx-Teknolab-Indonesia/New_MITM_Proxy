@echo off
REM Jalankan Mini MITM Proxy di Windows
where py >nul 2>nul && (py -3.12 app.py) || (python app.py)
pause
