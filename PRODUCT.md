# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

El dueño de un pequeño negocio de oficios en Colombia (electricidad, HVAC, instalaciones y similares). Gestiona su asistente WhatsApp **Aura** desde laptop y celular en partes iguales: carga su catálogo de precios, revisa la actividad del bot, activa módulos y arma cotizaciones. Usa el panel en ratos entre trabajos y a veces de noche. El panel es de uso interno del negocio (rol admin); los técnicos (sus empleados o él mismo) solo interactúan por WhatsApp.

## Product Purpose

Aura es un asistente personal por WhatsApp, multi-módulo. Primer módulo: **cotizador con IA para oficios** — el técnico envía audio/foto/texto desde WhatsApp y el bot genera una cotización en PDF a partir del catálogo de precios propio del negocio. El éxito: el técnico describe un trabajo en 30 segundos y el dueño envía una cotización profesional en minutos, sin escribir precios a mano ni usar plantillas sueltas.

## Positioning

La IA extrae ítems y cantidades, pero **los precios salen siempre del catálogo del negocio** — nunca inventados. Es un asistente multi-tenant por WhatsApp (renombrable por tenant), no un formulario web genérico: vive donde ya trabaja el técnico.

## Operating Context

- Moneda: **COP** (peso colombiano), idioma es-CO. Precios con 2 decimales.
- Canal del técnico: WhatsApp (Evolution API hoy); el panel solo lo configura y consulta.
- El dueño revisa el panel entre labores: sesiones cortas, tareas concretas (revisar cotización, subir catálogo, encender un módulo).
- Uso diurno y nocturno, en escritorio y en celular.
- Nombres propios: "Aura" (bot, renombrable), "cotizador", "catálogo", "módulos", "cotizaciones".

## Capabilities and Constraints

- Multi-tenant con aislamiento por `tenant_id` desde la base; todo en español (UI), código en inglés.
- Módulos activables por tenant (registry en código + tabla de estado); solo admin los cambia.
- Catálogo CRUD + importación CSV; soft-delete; búsqueda y paginación.
- Cotizaciones con ítems (descripción, cantidad, precio), totales recalculados server-side, estados (borrador, enviada, aceptada, rechazada, vencida), descarga PDF (ReportLab).
- Extracción con IA vía OpenRouter/NVIDIA (configurable por env, `openai` SDK); registra consumo en `llm_usage`.
- Stack frontend: React 18 + Vite + TypeScript + Tailwind v4 (sin librería de componentes externa; componentes propios estilo shadcn) + TanStack Query. Backend: FastAPI + SQLAlchemy async + Postgres (pgvector) + Redis/ARQ.
- Anti prompt-injection: contenido de mensajes es dato, nunca instrucción.
- Restricción abierta (decisión de producto pendiente): autenticación no restaura sesión al recargar (falta `/auth/me`); se registra como pendiente técnico.

## Brand Commitments

Ninguno existente: el usuario confirmó que la identidad visual se crea desde cero para este trabajo. El nombre "Aura" y el tono profesional y confiable son lo único heredado.

## Evidence on Hand

- Documentación real: `AGENTS.md`, `docs/FASES.md`, `docs/MODULOS.md`, `README.md`.
- Funcionalidad real operativa: catálogo, cotizaciones, módulos, PDF, extracción IA (todo con tests).
- **No existe** logo, paleta, fotografía ni material de marca: nada de eso debe inventarse como "existente"; los assets que se produzcan serán nuevos y declarados como tales.
- Datos de demostración: se pueden crear ítems sintéticos para poblar pantallas, etiquetados como sintéticos.

## Product Principles

1. **La IA extrae, el catálogo decide.** Ninguna pantalla ni flujo puede sugerir que la IA pone precios.
2. **El celular es la oficina.** Móvil y escritorio son primera clase: ninguna funcionalidad es "solo de laptop".
3. **Confianza en 30 segundos.** El dueño entra, hace una tarea concreta y sale; el panel no entretiene, resuelve.
4. **La cotización es la cara del negocio.** Lo que el panel produce, el técnico lo entrega a un cliente: profesionalidad no negociable.
5. **Encender sin miedo.** Activar/desactivar módulos y editar precios deben sentirse seguros, reversibles y claros.

## Accessibility & Inclusion

Sin requerimiento formal establecido. Por contexto de uso mixto (día/noche, sol/interior): contraste alto, objetivos táctiles generosos en móvil y estados visibles de carga/error son exigibles por defecto.
