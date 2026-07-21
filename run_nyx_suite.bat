@echo off
REM Launch the Nyx Suite bridge (web dashboard + tray) on Windows.
REM First run sets up the venv, installs dependencies, and the Playwright browser.
cd /d "%~dp0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0portable_launch_nyx.ps1" -EntryScript bridge_app.py
set "exit_code=%ERRORLEVEL%"
if not "%exit_code%"=="0" pause
exit /b %exit_code%
