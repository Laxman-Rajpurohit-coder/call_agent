@echo off
title Superfone Voice Bot Launcher
echo ========================================================
echo   STARTING SUPERFONE AI VOICE BOT SERVICES
echo ========================================================

set ASTERISK_AMI_SECRET=F-yfV4qLZt7-fnA5qzlq0_z6lH9HBUlc
set WHISPER_MODEL=base

echo Freeing ports 9092, 9093, 9094, 9095, 9096...
powershell -Command "Get-NetTCPConnection -LocalPort 9092,9093,9094,9095,9096 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }"
ping -n 2 127.0.0.1 >nul

echo 1. Launching STT Worker (Port 9094)...
start "STT Worker (9094)" cmd /k "set WHISPER_MODEL=base&& .\venv\Scripts\python.exe -m services.stt.worker"

echo 2. Launching LLM Server (Port 9093)...
start "LLM Server (9093)" cmd /k ".\venv\Scripts\python.exe -m services.llm.server"

echo 3. Launching TTS Worker (Port 9095)...
start "TTS Worker (9095)" cmd /k ".\venv\Scripts\python.exe -m services.tts.worker"

echo 4. Launching Audio Studio (Port 9096)...
start "Audio Studio (9096)" cmd /k ".\venv\Scripts\python.exe -m services.audio_studio.studio_server"

echo Waiting for worker processes to initialize...
ping -n 4 127.0.0.1 >nul

echo 5. Launching Call Gateway (Port 9092)...
start "Call Gateway (9092)" cmd /k "set ASTERISK_AMI_SECRET=F-yfV4qLZt7-fnA5qzlq0_z6lH9HBUlc&& .\venv\Scripts\python.exe -m services.call_gateway.server"

echo ========================================================
echo   All 5 microservices launched successfully!
echo   AudioSocket Gateway: Port 9092
echo   Audio Studio Web UI: http://localhost:9096
echo ========================================================
