@echo off
REM WhatsApp Backup to CSV - Exportacion directa por linea de comandos
echo ========================================================
echo   WhatsApp Backup to CSV - Exportar Chats
echo ========================================================

uv run python -m src.cli export %*
pause
