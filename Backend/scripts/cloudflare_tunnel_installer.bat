@echo off
REM Cloudflare Tunnel Auto-Installer für Windows

echo ============================================
echo Cloudflare Tunnel Auto-Installer
echo ============================================
echo.

REM Prüfen ob Admin-Rechte vorhanden
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo Fehler: Administrator-Rechte erforderlich!
    echo Bitte mit Rechtsklick "Als Administrator ausführen" starten.
    pause
    exit /b 1
)

REM Python prüfen
python --version >nul 2>&1
if %errorLevel% neq 0 (
    echo Fehler: Python nicht gefunden!
    echo Bitte Python installieren: https://www.python.org/downloads/
    pause
    exit /b 1
)

REM Skript ausführen
python "%~dp0cloudflare_tunnel_installer.py"

pause
