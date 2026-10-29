# Arranca todo el proyecto Aura en orden: Docker → backend → panel.
# Uso: powershell -ExecutionPolicy Bypass -File .\arrancar.ps1
# (o pídele al agente: "arranca")

$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "== 1/4 Docker Desktop ==" -ForegroundColor Cyan
$dockerProc = Get-Process "Docker Desktop" -ErrorAction SilentlyContinue
if (-not $dockerProc) {
    Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"
}
$intentos = 0
do {
    Start-Sleep -Seconds 5
    $intentos++
    docker version --format "{{.Server.Version}}" *> $null
} while ($LASTEXITCODE -ne 0 -and $intentos -lt 36)
if ($LASTEXITCODE -ne 0) {
    Write-Host "Docker no respondio tras 3 min. Abre Docker Desktop a mano." -ForegroundColor Red
    exit 1
}
Write-Host "Engine listo ($intentos intentos)" -ForegroundColor Green

Write-Host "== 2/4 Contenedores (Postgres + Redis + Evolution) ==" -ForegroundColor Cyan
docker compose -f "$root\docker-compose.yml" up -d
Start-Sleep -Seconds 8
docker ps --format "{{.Names}}: {{.Status}}"

Write-Host "== 3/4 Backend :8000 ==" -ForegroundColor Cyan
$p8000 = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if ($p8000) {
    Write-Host "Ya hay algo en 8000: no toco nada." -ForegroundColor Yellow
} else {
    Start-Process -WorkingDirectory "$root\backend" -FilePath "$root\backend\.venv\Scripts\python.exe" `
        -ArgumentList "-m", "uvicorn", "app.main:app", "--port", "8000", "--loop", "asyncio:SelectorEventLoop" `
        -WindowStyle Hidden
}

Write-Host "== 4/4 Panel :5173 ==" -ForegroundColor Cyan
$p5173 = Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction SilentlyContinue
if ($p5173) {
    Write-Host "Ya hay algo en 5173: no toco nada." -ForegroundColor Yellow
} else {
    Start-Process -WorkingDirectory "$root\admin-web" -FilePath "cmd.exe" `
        -ArgumentList "/c", "npm run dev" -WindowStyle Hidden
}

Start-Sleep -Seconds 10
Write-Host "== Verificacion ==" -ForegroundColor Cyan
try { Invoke-RestMethod "http://127.0.0.1:8000/health" -TimeoutSec 10 | Out-Null; Write-Host "Backend OK" -ForegroundColor Green } catch { Write-Host "Backend SIN RESPUESTA" -ForegroundColor Red }
try { Invoke-WebRequest "http://localhost:5173" -UseBasicParsing -TimeoutSec 10 | Out-Null; Write-Host "Panel OK" -ForegroundColor Green } catch { Write-Host "Panel SIN RESPUESTA" -ForegroundColor Red }
Write-Host "Listo: http://localhost:5173" -ForegroundColor Cyan
