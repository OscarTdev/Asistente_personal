# Asistente Personal (Aura)

Asistente por WhatsApp multi-módulo para oficios en Colombia (electricidad, HVAC, instalaciones). El técnico escribe por WhatsApp y el bot cotiza desde su catálogo de precios, hace seguimiento a las cotizaciones y gestiona a sus clientes. Producto multi-tenant: **un solo número de WhatsApp** — el backend identifica al técnico por su número (`tenants.wa_id`) y le sirve su propio historial, catálogo y servicios según su plan.

## Estado actual (octubre 2026)

Construido y funcionando:
- **Cotizador con IA**: texto → extracción con LLM (NVIDIA NIM / OpenRouter, compatible OpenAI) → matching del catálogo → cotización en PDF por WhatsApp. La IA nunca inventa precios: sin match no se cotiza.
- **Seguimiento de cotizaciones**: el bot escribe al cliente a los 3 y 7 días (rondas anti-spam, configurable) y detecta cuando el cliente respondió.
- **Canal real**: Evolution API v2 en Docker (instancia Baileys con QR), webhook idempotente y autenticado por secreto compartido (`X-Webhook-Secret`).
- **Suscripciones**: planes trial → freemium → premium (COP $29.000/mes) con contrato de entitlements (nadie enciende un servicio fuera de su plan), métodos de pago tokenizados (PCI), link de pago de MercadoPago (Checkout Pro) y webhook de pagos con firma HMAC verificada.
- **Panel de administración**: React + Vite + Tailwind (tema conserje de boutique): catálogo, cotizaciones, clientes, seguimiento, servicios, conexión WhatsApp.
- **Multi-tenant**: todos los datos aislados por `tenant_id`; admin de la plataforma (`is_platform_admin`) gestiona planes, servicios y historial de chat de cada cliente.

En desarrollo: transcripción de audios (STT), recordatorios y agenda, página Admin del panel.

## Requisitos

- Docker Desktop (Postgres 16 + pgvector, Redis 7, Evolution API v2.3.7)
- Python 3.12+
- Node.js 18+

## Puesta en marcha

1. Copiar `.env.example` a `.env` y completar: `JWT_SECRET` (32+ caracteres; el texto de ejemplo no arranca), `LLM_API_KEY` (NVIDIA NIM u OpenRouter), `EVOLUTION_API_KEY`, `WEBHOOK_SECRET`.
2. `docker compose up -d` — Postgres queda en `127.0.0.1:5433` (el 5432 lo ocupa el PostgreSQL local de Windows), Redis en 6379 y Evolution en 8080, todos solo en localhost.
3. Backend:
   ```powershell
   cd backend
   python -m venv .venv
   .\.venv\Scripts\activate.ps1
   pip install -r requirements.txt -r requirements-dev.txt
   alembic upgrade head
   python -m scripts.create_admin --email admin@example.com --platform-admin --phone 573001234567
   uvicorn app.main:app --reload --port 8000 --loop asyncio:SelectorEventLoop
   ```
4. Frontend:
   ```powershell
   cd admin-web
   npm install
   npm run dev
   ```
5. Conectar WhatsApp: abrir http://localhost:5173 → Conexión → escanear el QR. Al conectar, configurar el webhook de Evolution con la cabecera `x-webhook-secret` (ver `backend/app/api/deps.py`).

## Tests y lint

```powershell
cd backend
pytest -v          # contra Postgres real (base de datos de prueba dedicada)
ruff check .
```

## Seguridad

- Webhook de WhatsApp **fail-closed**: sin `X-Webhook-Secret` correcto responde 401.
- Webhook de MercadoPago: firma HMAC (`x-signature`) verificada y el pago se consulta a la API de MP (nunca se confía en el cuerpo).
- Tarjetas: solo tokens de la pasarela (brand + últimos 4). El número jamás pasa por el servidor.
- Docker: todos los puertos publicados únicamente en `127.0.0.1`.

## Licencia

[MIT](LICENSE)
