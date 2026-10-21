# Asistente Personal — Documentación Completa

## Introducción

**Asistente Personal** (Aura) es un asistente por WhatsApp diseñado para
vender como servicio a múltiples negocios de oficios en Colombia
(electricidad, HVAC, instalaciones sanitarias, carpintería, etc.).

El técnico envía audios, fotos o textos desde WhatsApp y el asistente le
ayuda en su día a día: genera cotizaciones profesionales en PDF, hace
seguimiento de las cotizaciones enviadas a sus clientes, gestiona notas y
recordatorios, y se adapta a cada negocio.

La plataforma es **multi-tenant**: cada negocio de oficios es un "tenant"
con sus propios datos, conversaciones, catálogo de precios y
configuración aislada de los demás. El propietario de la plataforma
(Oscar) administra todos los negocios desde un panel de administración
con los permisos de `is_platform_admin`.

### Arquitectura de alto nivel

```
[WhatsApp] ── webhook firmado ──► [FastAPI (backend)] ──► [PostgreSQL + pgvector]
       ▲                                    │                        │
       │                                    ▼                        ▼
  [Evolution API]              [Redis + Workers ARQ]         [Panel React]
  (canal: Evolution v2,         (agrupación, seguimiento,      (dueños y
   instancia única)             recordatorios, pagos)          plataforma)
```

- **Un solo número de WhatsApp compartido** entre todos los tenants
  (Enmienda A). El remitente se identifica por su número
  (`channel_identities`) y enruta a SU tenant.
- **Monolito modular**: el backend es un solo servicio FastAPI, no
  microservicios. Los workers (seguimiento, recordatorios, vencimiento de
  planes) corren como tareas de fondo dentro del proceso (`asyncio`), con
  plan de migración a ARQ para producción.
- **Sin dependencia del canal**: notas, archivos, memoria, catálogo,
  conversaciones, cotizaciones y recordatorios viven en la base de datos
  (`channel_identities` hace la traducción entre canal y usuario). El
  mismo usuario puede hablarle por WhatsApp, Telegram o la app sin perder
  nada.

### Módulos construidos

| Módulo | Estado | Descripción |
|---|---|---|
| Cotizador con IA | ✅ Activo | Extracción de ítems con LLM → matching con catálogo → PDF |
| Seguimiento | ✅ Activo | Escritura a clientes a los 3 y 7 días, detección de respuesta |
| Registro por chat | ✅ Activo | Onboarding conversacional con consentimiento, tipo de cuenta, NIT |
| Notas | ✅ Activo | Guardar, buscar, listar y borrar notas por chat |
| Recordatorios | ✅ Activo | El bot escribe al dueño en la fecha programada |
| Cuenta de cobro | ✅ Activo | PDF de cobro con datos bancarios y total en letras |
| Suscripciones | ✅ Activo | Planes trial/freemium/premium, MercadoPago Checkout Pro |
| Audio (STT) | 🔄 STT construido | Transcripción con Groq Whisper (configurable) |
| Audio (TTS) | 🔄 Infra lista | Edge TTS gratis con voz es-CO-SalomeNeural |
| Panel plataforma | 🔄 Construyendo | Admin de plataforma: clientes, planes, chat |
| Instancia por canal | 🔄 Infra lista | `channel_identities` para Telegram/Cloud API |

---

## Guía de instalación

### Requisitos

- Docker Desktop
- Python 3.12+
- Node.js 18+

### Pasos

```powershell
# 1. Infraestructura
docker compose up -d

# 2. Backend
cd backend
python -m venv .venv
.\.venv\Scripts\activate.ps1
pip install -r requirements.txt -r requirements-dev.txt

# 3. Copiar variables de entorno
Copy-Item ..\.env.example ..\.env
# Editar .env: JWT_SECRET (32+ chars), LLM_API_KEY, WEBHOOK_SECRET, etc.

# 4. Migraciones
alembic upgrade head

# 5. Crear admin de plataforma
python -m scripts.create_admin --email admin@example.com --platform-admin

# 6. Iniciar backend (en una terminal)
uvicorn app.main:app --reload --port 8000 --loop asyncio:SelectorEventLoop

# 7. Iniciar panel (en otra terminal)
cd ..\admin-web
npm install
npm run dev
# → http://localhost:5173
```

---

## Documentación de la API

El backend expone documentación interactiva automática en:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

A continuación, la referencia completa de los endpoints agrupados por módulo.

### Autenticación

| Método | Ruta | Descripción | Auth |
|---|---|---|---|
| POST | `/api/v1/auth/login` | Login con email + contraseña (OAuth2) | — |
| POST | `/api/v1/auth/set-password` | Crea contraseña con token de un solo uso (onboarding) | — |

**Login** devuelve `access_token` (JWT) + datos del usuario
(incluye `is_platform_admin: bool`).

### Registro (onboarding por chat)

El registro ocurre automáticamente cuando un número desconocido le
escribe al bot. No requiere endpoint adicional: el orquestador detecta el
prospecto y arranca la conversación de registro.

| Paso | Qué pide el bot |
|---|---|
| Consentimiento | «Acepta nuestra política» (Ley 1581, se registra en `consents`) |
| Nombre del asistente | «¿Cómo quieres que me llame?» |
| Tipo de cuenta | «¿Eres persona natural o negocio?» (1 o 2) |
| NIT (solo negocio) | Con dígito de verificación DIAN validado |
| Nombre del dueño | «¿Cómo prefieres que te llame?» |
| Ciudad | Para el perfil del negocio |
| Correo | Para notificaciones y facturación |
| Preferencia de respuesta | Texto, audio o automático |
| **Enlace de contraseña** | Token JWT de un solo uso (30 min) → `/crear-contrasena?token=...` |

### Webhooks

| Método | Ruta | Descripción | Auth |
|---|---|---|---|
| POST | `/api/v1/webhooks/whatsapp` | Webhook de Evolution API (mensajes) | `X-Webhook-Secret` header |
| POST | `/api/v1/webhooks/payments/mercadopago` | Webhook de pagos de MP | HMAC con `x-signature` |

**Webhook de WhatsApp (fail-closed):**
- Sin `X-Webhook-Secret` → 401. Sin el secreto configurado en el
  servidor → 401. Secreto incorrecto → 401.
- Responde 200 de inmediato; el cerebro corre en background.
- Idempotencia: `UNIQUE(tenant_id, whatsapp_message_id)`.
- El remitente se resuelve por `channel_identities` (no por slug):
  desconocido → tenant de plataforma; conocido → SU tenant.

**Webhook de MercadoPago:**
- Firma HMAC verificada con `MERCADOPAGO_WEBHOOK_SECRET` (ventana de 5 min).
- Guarda el evento primero (`payment_webhook_events` con
  `UNIQUE(provider, provider_ref)`), procesa después en background.
- Solo aplica el plan premium al tenant que pagó (por
  `external_reference`).

### Cotizador

| Método | Ruta | Descripción | Auth |
|---|---|---|---|
| POST | `/api/v1/quotes` | Crear cotización con ítems | JWT (admin del tenant) |
| GET | `/api/v1/quotes` | Listar cotizaciones del tenant | JWT |
| GET | `/api/v1/quotes/{id}` | Detalle de cotización con ítems | JWT |
| PUT | `/api/v1/quotes/{id}` | Actualizar estado o notas | JWT |
| GET | `/api/v1/quotes/{id}/pdf` | Descargar PDF de la cotización | JWT |
| POST | `/api/v1/quotes/{id}/items` | Agregar ítem | JWT |
| PUT | `/api/v1/quotes/{id}/items/{item_id}` | Actualizar ítem | JWT |
| DELETE | `/api/v1/quotes/{id}/items/{item_id}` | Eliminar ítem | JWT |
| POST | `/api/v1/quotes/extract` | Extraer ítems con IA desde texto | JWT |

### Catálogo

| Método | Ruta | Descripción | Auth |
|---|---|---|---|
| GET | `/api/v1/catalog` | Listar ítems del catálogo | JWT |
| POST | `/api/v1/catalog` | Crear ítem | JWT (admin) |
| PUT | `/api/v1/catalog/{id}` | Actualizar ítem | JWT (admin) |
| DELETE | `/api/v1/catalog/{id}` | Eliminar ítem (soft) | JWT (admin) |
| POST | `/api/v1/catalog/import-csv` | Carga masiva desde CSV | JWT (admin) |

### Seguimiento

| Método | Ruta | Descripción | Auth |
|---|---|---|---|
| GET | `/api/v1/followup/pending` | Cotizaciones pendientes de seguimiento | JWT |
| POST | `/api/v1/followup/run` | Ejecutar ronda manual | JWT (admin) |

### Dashboard

| Método | Ruta | Descripción | Auth |
|---|---|---|---|
| GET | `/api/v1/dashboard/stats` | Métricas del tenant | JWT |

### WhatsApp (conexión)

| Método | Ruta | Descripción | Auth |
|---|---|---|---|
| GET | `/api/v1/whatsapp/status` | Estado de la instancia | JWT |
| POST | `/api/v1/whatsapp/connect` | Iniciar emparejamiento (QR) | JWT (admin) |
| POST | `/api/v1/whatsapp/disconnect` | Cerrar sesión de WhatsApp | JWT (admin) |
| POST | `/api/v1/whatsapp/test-send` | Enviar mensaje de prueba | JWT (admin) |

### Módulos

| Método | Ruta | Descripción | Auth |
|---|---|---|---|
| GET | `/api/v1/modules` | Lista de módulos con estado por tenant | JWT |
| PUT | `/api/v1/modules/{key}` | Activar/desactivar módulo | JWT (admin) |

### Google Workspace (conexión del dueño — guía: `docs/GOOGLE.md`)

| Método | Ruta | Descripción | Auth |
|---|---|---|---|
| GET | `/api/v1/google/status` | ¿Conectado? correo y scopes del tenant | JWT |
| POST | `/api/v1/google/authorize` | URL de consentimiento (state JWT 10 min) | JWT (admin) |
| POST | `/api/v1/google/callback` | Canjea el code y guarda los tokens | JWT (admin) |
| DELETE | `/api/v1/google/disconnect` | Revoca en Google y borra la conexión | JWT (admin) |
| GET | `/api/v1/google/gmail/summary` | Correos recientes de la bandeja | JWT (admin) |
| GET | `/api/v1/google/calendar/upcoming` | Agenda de los próximos días | JWT (admin) |
| POST | `/api/v1/google/calendar/events` | Crear evento (naive = hora Colombia) | JWT (admin) |
| POST | `/api/v1/google/sheets/export-expenses` | Gastos del mes → hoja de cálculo | JWT (admin) |
| POST | `/api/v1/google/docs/month-report` | Informe del mes → Google Doc | JWT (admin) |
| GET | `/api/v1/google/drive/files` | Archivos recientes del Drive | JWT (admin) |
| POST | `/api/v1/google/forms/satisfaction-survey` | Encuesta de satisfacción (Forms) | JWT (admin) |

Errores: `409` = sin conexión o sesión Google expirada (reconectar en el
panel), `422` = plataforma sin credenciales, `502` = Google respondió
con error. Una cuenta Google por tenant (`google_connections`,
UNIQUE `tenant_id`); el correo a un tercero siempre pide confirmación.

### Admin de plataforma (solo `is_platform_admin`)

| Método | Ruta | Descripción | Auth |
|---|---|---|---|
| GET | `/api/v1/admin/tenants` | Lista todos los negocios con uso | Platform admin |
| GET | `/api/v1/admin/tenants/{id}` | Detalle: servicios, pagos, suscripción | Platform admin |
| PATCH | `/api/v1/admin/tenants/{id}` | Editar nombre, bot, customer_mode | Platform admin |
| PATCH | `/api/v1/admin/tenants/{id}/plan` | Cambiar plan (sincroniza módulos) | Platform admin |
| PUT | `/api/v1/admin/tenants/{id}/whatsapp` | Registrar/cambiar número del dueño | Platform admin |
| POST | `/api/v1/admin/tenants/{id}/payment-method` | Registrar método de pago (manual) | Platform admin |
| DELETE | `/api/v1/admin/tenants/{id}/payment-methods/{pm_id}` | Desvincular método de pago | Platform admin |
| POST | `/api/v1/admin/tenants/{id}/checkout-link` | Generar link de pago MP | Platform admin |
| PUT | `/api/v1/admin/tenants/{id}/modules/{key}` | Activar/desactivar servicio | Platform admin |
| GET | `/api/v1/admin/tenants/{id}/conversations` | Historial de chat | Platform admin |
| GET | `/api/v1/admin/tenants/{id}/conversations/{conv_id}/messages` | Mensajes de una conversación | Platform admin |
| GET | `/api/v1/admin/tenants/{id}/contacts/{contact_id}/identities` | Identidades del contacto | Platform admin |
| POST | `/api/v1/admin/tenants/{id}/contacts/{contact_id}/identities` | Vincular identidad de canal | Platform admin |
| DELETE | `/api/v1/admin/tenants/{id}/identities/{identity_id}` | Desvincular identidad | Platform admin |

---

## Arquitectura interna del backend

```
backend/app/
├── api/v1/          # Routers FastAPI versionados en /api/v1
│   ├── admin.py     → Gestión de plataforma (solo is_platform_admin)
│   ├── auth.py      → Login, set-password con token de un solo uso
│   ├── catalog.py   → CRUD del catálogo de precios
│   ├── contacts.py  → CRM del dueño (clientes finales)
│   ├── dashboard.py → Métricas del panel
│   ├── followup.py  → Seguimiento de cotizaciones (manual + programado)
│   ├── modules.py   → Módulos del asistente por tenant
│   ├── quotes.py    → Cotizaciones e ítems
│   ├── webhooks.py  → Webhooks de WhatsApp (Evolution) y MercadoPago
│   └── whatsapp.py  → Conexión WhatsApp del panel
├── channels/        → Capa de canal abstracta
│   ├── base.py      → ABC Channel: send_text, send_document, parse_incoming
│   └── evolution.py → Implementación para Evolution API v2
├── core/
│   ├── config.py    → Settings con pydantic (fail-fast JWT, sin defaults de claves)
│   ├── database.py  → SQLAlchemy async engine + SessionFactory
│   ├── nit.py       → Validador de NIT colombiano (dígito de verificación DIAN)
│   ├── redis.py     → Cliente Redis async
│   └── security.py  → JWT, hash de contraseñas (passlib+bcrypt)
├── models/          → Modelos SQLAlchemy (16 tablas)
├── schemas/         → Esquemas Pydantic (entrada/salida de la API)
├── services/        → Lógica de negocio
│   ├── ai_extraction.py    → Extracción de ítems con LLM + matching del catálogo
│   ├── assistant.py        → Router de intenciones del dueño (LLM clasifica)
│   ├── audio.py            → STT (transcripción) y TTS (síntesis) configurables
│   ├── debounce.py         → Agrupación de mensajes (5s silencio, tope 20s)
│   ├── documents.py        → Consecutivos, snapshot inmutable, total en letras
│   ├── entitlements.py     → Planes → módulos autorizados (aplicar/quitar)
│   ├── events.py           → Publicación de eventos en Redis pub/sub
│   ├── followup.py         → Motor de seguimiento 3 y 7 días
│   ├── identity.py         → Resolución channel_identities (multi-canal)
│   ├── invoice_pdf.py      → Generador de cuenta de cobro CC-0001
│   ├── mercadopago.py      → Webhook de pagos: firma, fetch, idempotencia
│   ├── messages.py         → Ingesta idempotente de mensajes + routing
│   ├── notes.py            → Notas y recordatorios (guardar, buscar, borrar)
│   ├── onboarding.py       → Registro conversacional (consentimiento, NIT, etc.)
│   ├── orchestrator.py     → Cerebro del bot: roles, intenciones, confirmación
│   ├── pdf_generator.py    → Generador de cotización PDF (ReportLab)
│   ├── quotes.py           → Creación de cotizaciones
│   ├── usage.py            → Registro de consumo por servicio
├── schemas/         → Modelos Pydantic de entrada/salida
├── workers/         → Tareas de fondo (planeado: ARQ)
└── main.py          → FastAPI + lifespan (scheduler de fondo)
```

### Flujo de un mensaje de WhatsApp

```
1. Evolution API envía el webhook POST /api/v1/webhooks/whatsapp
2. verify_webhook_secret → 401 si no coincide
3. channel.parse_incoming(payload) → IncomingMessage (wa_id, text, type)
4. identity_service.resolve_identity(channel="whatsapp", external_id=wa_id)
   → (tenant, contact, is_owner)
5. ingest_message: persiste Message (direction="in"), Event, dedupe
6. BackgroundTask: debounce engine
7. Después de 5s de silencio (o 20s tope):
   - Si hay audios: transcribir y unir al texto
   - Orchestrator.handle_incoming(texto unificado)
8. El orquestador decide el rol:
   - is_team_member → asistente (cotiza, envía, agenda)
   - prospecto nuevo → onboarding
   - cliente conocido → silencio o atención (customer_mode)
```

### Flujo de una cotización

```
Dueño: "Cotizale a Juliana 3 tomacorrientes dobles"
  │
  ├─ detect_intent → "quote" (contacto: "Juliana")
  ├─ extract_items_from_text → [Tomacorriente doble × 3]
  ├─ _match_catalog_item → "Tomacorriente doble" ($18.500) ✓ match
  │
  ├─ create_quote (draft, tenant=owner, contact=Juliana)
  ├─ next_document_number → COT-0001 (SELECT FOR UPDATE)
  ├─ create_document (snapshot JSONB inmutable)
  ├─ generate_quote_pdf (ReportLab, escape XML, total en letras)
  │
  ├─ _send_out_message (PDF al DUEÑO en SU chat)
  ├─ PendingAction(action_type="send_quote", payload={quote_id, contact_id})
  │
  └─ "📄 Lista tu cotización COT-0001 para Juliana. ¿Quieres que se la envíe?"

Dueño: "Sí, envíala"
  │
  ├─ _handle_confirmation → detecta "sí" + pending send_quote
  ├─ channel.send_document(Juliana.wa_id, PDF)
  ├─ quote.status = "sent", quote.sent_at = now
  └─ "✅ Envié COT-0001 a Juliana. El seguimiento le escribirá..."
```

---

## Base de datos

PostgreSQL 16 con pgvector (imagen `pgvector/pgvector:pg16`). 20 tablas:

| Tabla | Propósito |
|---|---|
| `tenants` | Negocios (cuentas de la plataforma) |
| `users` | Usuarios del panel (con `is_platform_admin`) |
| `tenant_modules` | Módulos activados por tenant (contrato de planes) |
| `contacts` | Clientes finales de cada negocio |
| `conversations` | Chats entre bot y contactos |
| `messages` | Mensajes individuales de cada conversación |
| `catalog_items` | Catálogo de precios del negocio |
| `quotes` | Cotizaciones (draft → sent → accepted/rejected) |
| `quote_items` | Ítems de cada cotización |
| `follow_ups` | Rondas de seguimiento 3 y 7 días |
| `events` | Feed de eventos del panel (WebSocket) |
| `llm_usage` | Consumo de tokens IA por tenant |
| `service_usage` | Interacciones por servicio |
| `subscriptions` | Historial de cambios de plan |
| `payment_methods` | Métodos de pago tokenizados |
| `channel_identities` | Traducción canal → usuario (multi-canal) |
| `consents` | Registro de consentimientos (Ley 1581) |
| `onboarding_sessions` | Máquina de estados del registro |
| `documents` | Documentos emitidos con snapshot inmutable |
| `document_counters` | Consecutivos por negocio y tipo (COT/CC) |
| `tenant_branding` | Pie de página, color, datos bancarios |
| `pending_actions` | Acciones pendientes de confirmación del dueño |
| `payment_webhook_events` | Eventos de pago (idempotencia real) |

---

## Notas y recordatorios (spec §13)

Los dueños gestionan sus notas y recordatorios **por chat**, sin panel:

```
Dueño: "Guarda una nota: comprar 20 metros de cable THHN"
Bot: "📝 Anotado: «comprar 20 metros de cable THHN»"

Dueño: "Qué notas tengo"
Bot: "📝 Tus últimas notas: 1. Comprar cable... 2. Llamar a Juliana..."

Dueño: "Recuérdame llamar a Juliana el jueves a las 3"
Bot: "⏰ Listo: te recordaré «Llamar a Juliana» el 16/10 a las 3:00 PM."
     (el bot envía el recordatorio automáticamente en la fecha)
```

Los recordatorios se procesan en el loop de fondo cada 5 minutos:
se envía por WhatsApp al dueño, se marca como `sent`, y el próximo
cierre de sesión lo consume del feed de eventos.

---

## Seguridad

- **Webhook WhatsApp**: fail-closed, `X-Webhook-Secret` con
  `hmac.compare_digest`. Sin modo abierto.
- **Webhook MercadoPago**: HMAC con `x-signature`, ventana de 5 min,
  firma con id en minúsculas para ids alfanuméricos.
- **Contraseñas**: bcrypt (passlib), nunca viajan por WhatsApp.
- **JWT**: mínimo 32 caracteres validado al arrancar, expiración 24h.
- **Docker**: puertos solo en `127.0.0.1`, sin claves por defecto,
  versión fija de imágenes.
- **Habeas Data (Ley 1581)**: consentimiento registrado, sin teléfonos
  en logs, sin datos personales en eventos.
