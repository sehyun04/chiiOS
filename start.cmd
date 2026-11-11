@echo off
wsl.exe -d Debian --exec systemctl is-system-running --wait >nul
set "URL=http://localhost:7682/"
reg query "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe" >nul 2>&1 && goto edge
reg query "HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe" >nul 2>&1 && goto edge
start "" "%URL%"
exit /b
:edge
start "" msedge --app=%URL%
