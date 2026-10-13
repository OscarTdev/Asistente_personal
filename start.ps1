# ============================================================
#  Arranca el proyecto Asistente Personal completo
#  Uso: clic derecho > "Ejecutar con PowerShell"  (o: .\start.ps1)
# ============================================================

$root = $PSScriptRoot

Write-Host ""
Write-Host "[1/3] Infraestructura (Postgres + Redis + Evolution API)..." -ForegroundColor Green
docker compose -f "$root\docker-compose.yml" up -d

Write-Host "[2/3] Backend (http://localhost:8000)..." -ForegroundColor Green
Start-Process powershell -ArgumentList `
  "-NoExit", `
  "-Command", "cd '$root\backend'; Write-Host 'BACKEND - deja esta ventana abierta' -ForegroundColor Yellow; .\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000 --loop asyncio:SelectorEventLoop"

Write-Host "[3/3] Frontend (http://localhost:5173)..." -ForegroundColor Green
Start-Process powershell -ArgumentList `
  "-NoExit", `
  "-Command", "cd '$root\admin-web'; Write-Host 'FRONTEND - deja esta ventana abierta' -ForegroundColor Yellow; npm run dev -- --port 5173 --strictPort"

Write-Host ""
Write-Host "Espera ~20 segundos y abre:" -ForegroundColor Cyan
Write-Host "  Panel:    http://localhost:5173"   -ForegroundColor White
Write-Host "  API docs: http://localhost:8000/docs" -ForegroundColor White
Write-Host ""
Write-Host "Conexión WhatsApp: Panel > Conexión (admin) > Vincular número > escanea el QR"
Write-Host ""
