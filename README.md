# Asistente Personal

Proyecto de asistente personal por WhatsApp.

## Descripción

Asistente personal por WhatsApp, concebido como producto multi-módulo. El primer módulo es un cotizador con IA para oficios (electricidad, HVAC, instalaciones) en Colombia: el técnico envía audio, foto o texto y el bot genera una cotización en PDF usando un catálogo de precios propio.

En esta fase (Fase 1) hemos construido el esqueleto de punta a punta con:

- Docker Compose (Postgres/pgvector + Redis)
- Backend FastAPI con 10 tablas (todas con `tenant_id` salvo `tenants`)
- Autenticación JWT
- Webhook de WhatsApp idempotente
- Canal de abstracción (Evolution API stub)
- WebSocket de eventos en tiempo real
- Script de seed para crear tenant y admin
- Panel de administración en React (login + feed de eventos en vivo)
- Tests automatizados

## Estado actual

Esta implementación corresponde a la Fase 1 — Esqueleto de punta a punta, tal como se describe en `docs/FASES.md`.

## Requisitos

- Docker Desktop
- Python 3.12+
- Node.js 16+

## Instalación

1. Clonar el repositorio
2. Copiar `.env.example` a `.env` y establecer un `JWT_SECRET` real
   (Postgres corre en el puerto host **5433**, porque el 5432 suele estar ocupado
   por el servicio PostgreSQL local de Windows)
3. Ejecutar `docker compose up -d` para iniciar Postgres y Redis
4. Crear el entorno virtual de Python y instalar dependencias:
   ```bash
   cd backend
   python -m venv .venv
   source .venv/bin/activate   # o .\.venv\Scripts\activate.ps1 en Windows
   pip install -r requirements.txt -r requirements-dev.txt
   ```
5. Ejecutar las migraciones de la base de datos:
   ```bash
   alembic upgrade head
   ```
6. Crear el tenant y el usuario admin:
   ```bash
   python -m scripts.create_admin --email admin@example.com
   ```
   (se le pedirá la contraseña)
7. Iniciar el backend:
   ```bash
   uvicorn app.main:app --reload --port 8000 --loop asyncio:SelectorEventLoop
   # o alternativamente: python -m app.main
   ```
8. En otra terminal, instalar y ejecutar el frontend:
   ```bash
   cd ../admin-web
   npm install
   npm run dev
   ```
9. Abrir http://localhost:5173 e iniciar sesión con las credenciales creadas.

## Uso

- El backend estará disponible en http://localhost:8000
- El frontend en http://localhost:5173
- El webhook de WhatsApp (para pruebas) está en http://localhost:8000/api/v1/webhooks/whatsapp
- El WebSocket de eventos está en ws://localhost:8000/ws/events?token=<JWT>

## Tests y lint

Ejecutar los tests del backend:
```bash
cd backend
pytest -v
```

Lint y formato con ruff:
```bash
cd backend
ruff check .
```

## Alcance de la Fase 1

Ver `docs/FASES.md` para el alcance exacto de la Fase 1.

## Licencia

[MIT](https://choosealicense.com/licenses/mit/)