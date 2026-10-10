# Fases de construcción — Asistente Personal

## Antes de empezar

- Docker Desktop debe estar abierto.
- Usar modo plan (Shift+Tab) para cada fase nueva: primero el plan, después la aprobación, después el código.
- Un commit por fase; si algo sale mal, se vuelve atrás sin dolor.
- Las claves (API de Anthropic, tokens de WhatsApp) van solo en `.env`, nunca en el chat ni en el repo.
- Si algo falla, pasar el error completo y pedir reproducirlo antes de corregir.
- Si el plan parece demasiado grande, partirlo en pasos más pequeños.

## Fase 1 — Esqueleto funcionando de punta a punta

> Prompt para pedir la fase (usar tal cual):

```text
Lee CLAUDE.md. Vamos a construir el proyecto por fases. Hoy solo la FASE 1: el esqueleto
funcionando de punta a punta. Primero muéstrame un plan y espera mi aprobación.

FASE 1:
1. Raíz: docker-compose.yml (postgres con imagen pgvector/pgvector:pg16 con healthcheck, y redis:7-alpine,
   con volúmenes persistentes), .env.example, .gitignore y README con los comandos.
2. Backend (backend/): config con pydantic-settings, conexión async a Postgres, Alembic inicializado
   y una migración inicial con estas tablas (todas con tenant_id salvo tenants):
   tenants (incluye bot_name con default 'Aura'), users, contacts, conversations, messages,
   catalog_items, quotes, quote_items, events, llm_usage.
3. Endpoints: GET /health, POST /api/v1/auth/login (JWT con roles), y
   POST /api/v1/webhooks/whatsapp que guarde el mensaje de forma idempotente y publique
   un evento en Redis.
4. Capa de canal abstracta (channels/base.py) y una implementación stub de Evolution API.
5. WebSocket /ws/events que transmita en vivo los eventos publicados.
6. Un comando o script para crear el primer tenant y el usuario admin.
7. Frontend (admin-web/): Vite + React + TypeScript + Tailwind + shadcn/ui + TanStack Query +
   react-router. Pantallas: Login y un Dashboard con un feed de mensajes en vivo
   conectado al WebSocket.
8. Pruebas con pytest: health y la idempotencia del webhook.

Requisitos: al terminar, verifica que todo corre (docker compose up -d, alembic upgrade head,
uvicorn, npm run dev, pytest) y dime qué comandos ejecutaste y qué resultado dieron.
No avances a otras fases ni agregues funciones que no pedí.
```

## Fase 2 — Catálogo y cotización

Catálogo de precios (CRUD y carga por CSV) y extracción con IA, para generar la cotización en PDF.

## Fase 3 — Canal real

Conectar Evolution API real (en Docker), audios con transcripción, onboarding del nombre del bot (le pregunta al usuario cómo llamarlo; default «Aura») y toma de control humana.

## Fase 4 — Analítica

Estadísticas, editor del prompt, seguimientos automáticos.
