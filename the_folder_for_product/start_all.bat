@echo off
title Superfone Voice Bot Launcher
echo ========================================================
echo   STARTING ALL SUPERFONE AI VOICE BOT SERVICES
echo ========================================================

cd /d "%~dp0"

powershell -ExecutionPolicy Bypass -File "%~dp0start_all.ps1"
pause
