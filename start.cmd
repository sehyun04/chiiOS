@echo off
wsl.exe -d Debian --exec systemctl is-system-running --wait >nul
start "" http://localhost:7681
