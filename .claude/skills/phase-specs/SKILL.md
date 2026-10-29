---
name: phase-specs
description: Especificaciones completas de cada fase de construcción del asistente (Fases 1–4). Úsala cuando necesites el prompt detallado de una fase.
---

# Especificaciones de Fases — Asistente Personal

## Fase 1 — Esqueleto de punta a punta
- docker-compose (Postgres/pgvector, Redis)
- Tablas base con `tenant_id`
- Auth JWT
- Webhook de WhatsApp idempotente
- Capa de canal abstracta
- WebSocket de eventos
- Login + Dashboard en React
- Tests

## Fase 2 — Catálogo y cotización
- CRUD del catálogo de precios con carga por CSV
- Extracción con IA y cotización en PDF

## Fase 3 — Canal real
- Evolution API en Docker
- Transcripción de audios
- Onboarding del nombre del bot (default «Aura»)
- Toma de control humana

## Fase 4 — Analítica
- Estadísticas
- Editor del prompt
- Seguimientos automáticos

Prompt completo original en `docs/FASES.md`.