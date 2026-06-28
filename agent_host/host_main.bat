@echo off
REM Native messaging host launcher. Prefer the project venv Python, then the py
REM launcher, then python on PATH. Output must stay clean (host protocol only).
set "HD=%~dp0"
if exist "%HD%..\venv\Scripts\python.exe" (
  "%HD%..\venv\Scripts\python.exe" "%HD%host_main.py"
  goto :eof
)
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 "%HD%host_main.py"
  goto :eof
)
python "%HD%host_main.py"
