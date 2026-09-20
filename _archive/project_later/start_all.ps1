Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "  STARTING SUPERFONE AI VOICE BOT SERVICES (PowerShell)" -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan

$env:ASTERISK_AMI_SECRET = "F-yfV4qLZt7-fnA5qzlq0_z6lH9HBUlc"
$py = ".\venv\Scripts\python.exe"

Write-Host "1. Launching STT Worker (Faster-Whisper on Port 9094)..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "& '$py' -m services.stt.worker"

Write-Host "2. Launching LLM Server (Port 9093)..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "& '$py' -m services.llm.server"

Write-Host "3. Launching TTS Worker (Piper on Port 9095)..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "& '$py' -m services.tts.worker"

Write-Host "Waiting 3 seconds for workers to initialize..."
Start-Sleep -Seconds 3

Write-Host "4. Launching Call Gateway (AudioSocket on Port 9092)..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", "`$env:ASTERISK_AMI_SECRET='F-yfV4qLZt7-fnA5qzlq0_z6lH9HBUlc'; & '$py' -m services.call_gateway.server"

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "  All services started! AudioSocket is ready on 9092." -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan
