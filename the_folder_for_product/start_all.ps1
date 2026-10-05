$ErrorActionPreference = "SilentlyContinue"
$root = $PSScriptRoot
if (-not $root) { $root = "d:\snazzy it worksj\voice_agent\the_folder_for_product" }
Set-Location $root

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "  STARTING ALL SUPERFONE AI SERVICES & WEB PLATFORM" -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan

$py = if (Test-Path "$root\venv\Scripts\python.exe") { "$root\venv\Scripts\python.exe" } elseif (Test-Path "$root\..\venv\Scripts\python.exe") { (Resolve-Path "$root\..\venv\Scripts\python.exe").Path } else { "python.exe" }
Write-Host "Python binary: $py" -ForegroundColor Gray

# Set PYTHONPATH and load .env configuration
$env:PYTHONPATH = "$root;$env:PYTHONPATH"
$possibleEnvs = @("$root\.env", "$root\..\.env", "c:\daily_works\superfone_call\.env")
foreach ($envFile in $possibleEnvs) {
    if (Test-Path $envFile) {
        Get-Content $envFile | ForEach-Object {
            $line = $_.Trim()
            if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
                $parts = $line.Split("=", 2)
                [System.Environment]::SetEnvironmentVariable($parts[0].Trim(), $parts[1].Trim().Trim('"').Trim("'"), "Process")
            }
        }
        Write-Host "Loaded environment from: $envFile" -ForegroundColor Gray
        break
    }
}

# Free any lingering ports first
$ports = 3000, 8080, 9090, 9092, 9093, 9094, 9095, 9098
Get-NetTCPConnection -LocalPort $ports -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object {
    Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue
}
Start-Sleep -Seconds 1

# 1. Dashboard Platform (Port 9090)
Write-Host "1. Starting Dashboard Backend (Port 9090)..." -ForegroundColor Yellow
Start-Process -FilePath $py -ArgumentList "-m", "uvicorn", "services.dashboard.app.main:app", "--port", "9090", "--host", "0.0.0.0" -WorkingDirectory $root -WindowStyle Hidden

# 2. Node Express CRM Server (Port 8080)
Write-Host "2. Starting Voice Agent & CRM Server (Port 8080)..." -ForegroundColor Yellow
Start-Process -FilePath "node" -ArgumentList "server.js" -WorkingDirectory $root -WindowStyle Hidden

# 3. React Frontend (Port 3000)
Write-Host "3. Starting React Frontend Dashboard (Port 3000)..." -ForegroundColor Yellow
$npmCmd = if ($IsWindows -or $env:OS -like "*Windows*") { "npm.cmd" } else { "npm" }
Start-Process -FilePath $npmCmd -ArgumentList "run", "dev" -WorkingDirectory "$root\frontend" -WindowStyle Hidden

# 4. LLM Server (Port 9093)
Write-Host "4. Starting Conversation LLM Server (Port 9093)..." -ForegroundColor Yellow
Start-Process -FilePath $py -ArgumentList "-m", "services.llm.server" -WorkingDirectory $root -WindowStyle Hidden

# 5. STT Cloud Worker (Port 9094)
Write-Host "5. Starting STT Worker (Port 9094)..." -ForegroundColor Yellow
Start-Process -FilePath $py -ArgumentList "-m", "services.stt.worker" -WorkingDirectory $root -WindowStyle Hidden

# 6. Neural TTS Worker (Port 9095)
Write-Host "6. Starting TTS Worker (Port 9095)..." -ForegroundColor Yellow
Start-Process -FilePath $py -ArgumentList "-m", "services.tts.worker" -WorkingDirectory $root -WindowStyle Hidden

# 7. Call Gateway (Port 9092)
Write-Host "7. Starting Call Gateway (Port 9092)..." -ForegroundColor Yellow
$env:ASTERISK_AMI_SECRET = "F-yfV4qLZt7-fnA5qzlq0_z6lH9HBUlc"
Start-Process -FilePath $py -ArgumentList "-m", "services.call_gateway.server" -WorkingDirectory $root -WindowStyle Hidden

# 8. Vobiz WS Bridge (Port 9098)
Write-Host "8. Starting Vobiz WebSocket Bridge (Port 9098)..." -ForegroundColor Yellow
Start-Process -FilePath $py -ArgumentList "-m", "services.vobiz_bridge.server" -WorkingDirectory $root -WindowStyle Hidden

# 9. Ngrok Tunnel (Port 9098)
Write-Host "9. Starting Ngrok Tunnel (Port 9098 -> drool-envoy-sandy.ngrok-free.dev)..." -ForegroundColor Yellow
Start-Process -FilePath "ngrok" -ArgumentList "http", "9098", "--url", "drool-envoy-sandy.ngrok-free.dev" -WindowStyle Hidden

Write-Host "========================================================" -ForegroundColor Green
Write-Host "  All services launched in independent processes!" -ForegroundColor Green
Write-Host "  Frontend Dashboard : http://localhost:3000" -ForegroundColor Cyan
Write-Host "  Platform API       : http://localhost:9090" -ForegroundColor Cyan
Write-Host "  Express CRM API    : http://localhost:8080" -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Green
