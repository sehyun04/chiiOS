@echo off
wsl.exe -d Debian --exec systemctl is-system-running --wait >nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0open.ps1"
