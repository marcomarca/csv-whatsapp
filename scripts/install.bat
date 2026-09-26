@echo off
REM WhatsApp Backup to CSV - Script de instalacion y preparacion de dependencias
echo ========================================================
echo   WhatsApp Backup to CSV - Instalador de dependencias
echo ========================================================

where uv >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [!] 'uv' no esta instalado. Instalando uv o usando Python directo...
    pip install uv
)

echo [*] Sincronizando dependencias con uv...
uv sync --all-extras

echo.
echo [*] Comprobando instalacion...
uv run python -m src.cli status

echo.
echo [OK] Entorno configurado correctamente.
pause
