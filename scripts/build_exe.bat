@echo off
REM WhatsApp Backup to CSV - Compilador de ejecutable portable (.exe)
echo ========================================================
echo   WhatsApp Backup to CSV - Generador de EXE Portable
echo ========================================================

echo [*] Sincronizando dependencias...
uv sync --all-extras

echo [*] Compilando ejecutable standalone...
uv run pyinstaller whatsapp_backup.spec --clean --noconfirm

echo.
if %ERRORLEVEL% EQU 0 (
    echo [OK] Compilacion finalizada exitosamente.
    echo [OK] El archivo ejecutable esta listo en: dist\whatsapp-backup-csv.exe
) else (
    echo [ERROR] La compilacion ha fallado.
)
pause
