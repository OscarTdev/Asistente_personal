# Verificación final de la Fase 1
# Este script ejecuta la secuencia de verificación de la sección G del plan

# 1. Infra
Write-Host "1. Infra"
docker compose up -d
docker compose ps

# 2. Variables locales (una vez)
Write-Host "`n2. Variables locales"
Copy-Item .env.example .env
# Nota: el usuario debe editar .env y establecer un JWT_SECRET real

# 3. Venv (una vez)
Write-Host "`n3. Venv"
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-dev.txt

# 4. Migración (desde backend/)
Write-Host "`n4. Migración"
.\.venv\Scripts\alembic.exe upgrade head
# Verificar que se crearon las tablas
docker exec asistente_postgres psql -U asistente -d asistente -c "\dt"

# 5. Seed
Write-Host "`n5. Seed"
.#\.venv\Scripts\python.exe -m scripts.create_admin --tenant-name "Personal" --email admin@example.com
# Nota: el script pedirá la contraseña

# 6-7. Backend + health
Write-Host "`n6-7. Backend + health"
Start-Process .\.venv\Scripts\python.exe -ArgumentList "-m","uvicorn","app.main:app","--port","8000" -WorkingDirectory "." -RedirectStandardOutput "log.txt"
# Esperar a que el backend arranque
Start-Sleep -seconds 5
# Verificar el endpoint de salud
$healthResponse = Invoke-RestMethod -Uri "http://localhost:8000/health"
Write-Host "Health endpoint response: $healthResponse"

# 8. Login
Write-Host "`n8. Login"
$loginResponse = Invoke-RestMethod -Method Post -Uri "http://localhost:8000/api/v1/auth/login" -ContentType "application/json" -Body '{"email":"admin@example.com","password":"<la-del-seed>"}'
Write-Host "Login response: $loginResponse"
$token = $loginResponse.access_token

# 9. Webhook idempotente (¡dos veces, mismo key.id!)
Write-Host "`n9. Webhook idempotente"
$headers = @{ "X-Tenant-Slug" = "personal" }
$payload = '{"event":"messages.upsert","instance":"auratest","data":{"key":{"id":"3EB0F9B1B5D6C7D8","remoteJid":"573001234567@s.whatsapp.net","fromMe":false},"pushName":"Juan Pérez","messageType":"conversation","message":{"conversation":"Hola, necesito una cotización para un tablero"},"status":"RECEIVED"}}'
$response1 = Invoke-RestMethod -Method Post -Uri "http://localhost:8000/api/v1/webhooks/whatsapp" -Headers $headers -ContentType "application/json" -Body $payload
Write-Host "First webhook response: $response1"
$response2 = Invoke-RestMethod -Method Post -Uri "http://localhost:8000/api/v1/webhooks/whatsapp" -Headers $headers -ContentType "application/json" -Body $payload
Write-Host "Second webhook response: $response2"
# Verificar que la segunda respuesta tiene duplicate: true
if ($response2.duplicate -eq $true) {
    Write-Host "Idempotency verified: second request marked as duplicate"
} else {
    Write-Warning "Idempotency check failed: second request not marked as duplicate"
}
# Verificar que solo hay un mensaje en la base de datos
$messageCount = docker exec asistente_postgres psql -U asistente -d asistente -t -c "SELECT count(*) FROM messages;"
Write-Host "Message count: $messageCount"

# 10. Frontend
Write-Host "`n10. Frontend"
# Nota: el frontend debe ser ejecutado por el usuario en otra terminal
Write-Host "Por favor, ejecute en otra terminal:"
Write-Host "cd ..\admin-web"
Write-Host "npm install"
Write-Host "npm run dev"
Write-Host "Luego, abra http://localhost:5173 e inicie sesión"
Write-Host "Luego, repita el webhook con otro key.id para ver el mensaje en el feed"

# 11. Tests
Write-Host "`n11. Tests"
cd ..\backend
.#\.venv\Scripts\python.exe -m pytest -v

# 12. Lint
Write-Host "`n12. Lint"
.#\.venv\Scripts\python.exe -m ruff check .

# 13. WebSocket directo (opcional)
Write-Host "`n13. WebSocket directo (opcional)"
Write-Host "Para probar el WebSocket directamente, puede usar wscat:"
Write-Host "npx wscat -c \"ws://localhost:8000/ws/events?token=$token\""
Write-Host "Debería ver el mensaje de connected y luego los eventos de mensaje.recibido"

Write-Host "`nVerificación completada."