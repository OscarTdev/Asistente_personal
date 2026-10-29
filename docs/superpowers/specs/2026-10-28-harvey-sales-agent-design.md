# Spec: Harvey — Agente de Ventas Personal (Panel Admin)

**Fecha:** 2026-10-28
**Estado:** Aprobado para implementación
**Autor:** Juan David (dueño de la plataforma) + Claude Code

---

## 1. Contexto y Objetivo

**Harvey** es un módulo interno del panel de administración (`admin-web`) que le permite a **ti (dueño de la plataforma, ingeniero de software)** conseguir clientes para vender desarrollo de software, agentes de WhatsApp, bots, automatizaciones.

- Tú subes listas en Excel o configuras búsquedas en directorios (Google Maps, LinkedIn, Páginas Amarillas).
- Harvey scrapea/importa → crea leads en BD.
- Tú ves los leads en el panel (Kanban / tabla), filtras, seleccionas los que valen la pena.
- Harvey contacta por WhatsApp (outbound) a los seleccionados con plantilla personalizada.
- Harvey califica la respuesta con IA (BANT: presupuesto, autoridad, necesidad, timeline).
- Leads calificados → notificación a tu WhatsApp + panel → tú tomas la conversación y cierras.

**Multi-tenant:** Harvey corre en el **tenant de plataforma** (`is_platform=True`), aislado de los tenants de tus clientes técnicos.

---

## 2. Arquitectura General

```
┌─────────────────────────────────────────────────────────────────┐
│                      TENANT DE PLATAFORMA                        │
│  (is_platform=True, único, dueño = tú)                          │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │  LeadSource  │──▶│     Lead     │──▶│  OutreachCampaign    │  │
│  │  (Maps,      │    │  (nombre,    │    │  (plantilla,        │  │
│  │   LinkedIn,  │    │   empresa,   │    │   límite diario,    │  │
│  │   Excel)     │    │   teléfono,  │    │   horario)         │  │
│  └──────────────┘    │   email,     │    └──────────┬─────────┘  │
│         │            │   score,     │               │            │
│         ▼            │   estado)    │               ▼            │
│  ┌──────────────┐    └──────┬───────┘    ┌────────────────────┐  │
│  │  Scrapers    │           │            │  Outreach Engine   │  │
│  │  (modulares) │           ▼            │  (scheduler diario)│  │
│  └──────────────┘    ┌──────────────┐    └─────────┬──────────┘  │
│                      │  LeadQualif  │              │            │
│                      │  (IA + BANT) │              ▼            │
│                      └──────┬───────┘    ┌────────────────────┐  │
│                             │            │  Channel.send_text │  │
│                             ▼            │  (Evolution hoy,   │  │
│                      ┌──────────────┐   │   Cloud API mañana)│  │
│                      │  Notificac.  │   └────────────────────┘  │
│                      │  (tu WhatsApp│                             │
│                      │   + panel)   │                             │
│                      └──────────────┘                             │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Modelos de Datos (`backend/app/models/lead.py`)

### 3.1 LeadSource
```python
class LeadSource(Base):
    __tablename__ = "lead_sources"
    id: UUID (PK)
    tenant_id: UUID (FK → tenants.id, SIEMPRE tenant de plataforma)
    name: str                    # "Constructoras Medellín Maps"
    source_type: str             # "google_maps" | "linkedin" | "yellow_pages" | "excel_upload"
    config: JSONB                # {"query": "empresas constructoras Medellín", "max_results": 100}
    status: str                  # "idle" | "running" | "completed" | "failed"
    last_run_at: DateTime | None
    leads_found: int = 0
    leads_imported: int = 0
    created_at: DateTime
    updated_at: DateTime
```

### 3.2 Lead
```python
class Lead(Base):
    __tablename__ = "leads"
    id: UUID (PK)
    tenant_id: UUID (FK → tenants.id, SIEMPRE tenant de plataforma)
    source_id: UUID (FK → lead_sources.id, nullable)
    campaign_id: UUID (FK → outreach_campaigns.id, nullable)
    # Datos del prospecto
    full_name: str | None
    company_name: str | None
    phone: str                   # wa_id normalizado (573XXXXXXXXX)
    email: str | None
    address: str | None
    website: str | None
    # Metadatos
    source_type: str             # copia de source.source_type para queries rápidas
    raw_data: JSONB              # datos crudos del scraper (para re-procesar)
    # Estado del pipeline
    status: str                  # "new" | "contacted" | "replied" | "qualified" | "handoff" | "closed_won" | "closed_lost" | "opt_out"
    score: int = 0               # 0-100 (BANT score)
    notes: str | None            # notas tuyas manuales
    qualification: JSONB | None  # resultado IA: {"budget": "...", "authority": "...", "need": "...", "timeline": "...", "summary": "...", "recommendation": "handoff|nurture|discard"}
    # Tracking
    contacted_at: DateTime | None
    replied_at: DateTime | None
    qualified_at: DateTime | None
    created_at: DateTime
    updated_at: DateTime
    # Constraints
    __table_args__ = (UniqueConstraint("tenant_id", "phone", name="uq_lead_tenant_phone"),)
```

### 3.3 OutreachCampaign
```python
class OutreachCampaign(Base):
    __tablename__ = "outreach_campaigns"
    id: UUID (PK)
    tenant_id: UUID (FK → tenants.id, SIEMPRE tenant de plataforma)
    name: str                    # "Constructoras Medellín - Oct 2026"
    template: str                # "Hola {nombre}, vi que {empresa}..."
    daily_limit: int = 20        # máx envíos/día (anti-ban)
    min_delay_seconds: int = 30  # delay mínimo entre envíos
    max_delay_seconds: int = 120 # delay máximo (aleatorio)
    allowed_hours_start: int = 8 # hora Colombia (UTC-5)
    allowed_hours_end: int = 18  # hora Colombia
    status: str                  # "draft" | "active" | "paused" | "completed"
    total_leads: int = 0
    sent_count: int = 0
    replied_count: int = 0
    qualified_count: int = 0
    created_at: DateTime
    updated_at: DateTime
```

### 3.4 OutreachMessage
```python
class OutreachMessage(Base):
    __tablename__ = "outreach_messages"
    id: UUID (PK)
    tenant_id: UUID (FK → tenants.id)
    campaign_id: UUID (FK → outreach_campaigns.id)
    lead_id: UUID (FK → leads.id)
    wa_id: str                   # destinatario (para dedupe)
    content: str                 # mensaje enviado (con variables resueltas)
    status: str                  # "queued" | "sent" | "delivered" | "read" | "replied" | "failed"
    whatsapp_message_id: str | None  # id real de Evolution/Cloud API
    error: str | None
    sent_at: DateTime | None
    delivered_at: DateTime | None
    read_at: DateTime | None
    replied_at: DateTime | None
    created_at: DateTime
    # Constraints
    __table_args__ = (UniqueConstraint("tenant_id", "whatsapp_message_id", name="uq_outreach_msg_wa_id"),)
```

### 3.5 LeadQualification (embebido en Lead.qualification JSONB, no tabla aparte)
Estructura:
```json
{
  "budget": "tiene presupuesto confirmado / no mencionado / sin presupuesto",
  "authority": "es dueño / gerente / empleado / no claro",
  "need": "necesita bot WhatsApp / agente IA / automatización / software a medida / no claro",
  "timeline": "inmediato / 1 mes / 3 meses / explorando / no mencionado",
  "summary": "Resumen 2-3 líneas de la conversación",
  "recommendation": "handoff | nurture | discard",
  "confidence": 0.85,
  "analyzed_at": "2026-10-28T15:30:00Z"
}
```

---

## 4. Servicios Backend (`backend/app/services/`)

### 4.1 `scraper.py` — Scrapers Modulares
```python
class BaseScraper(ABC):
    @abstractmethod
    async def search(self, config: dict) -> list[LeadCreate]: ...

class GoogleMapsScraper(BaseScraper):
    # Usa Places API (requiere GOOGLE_PLACES_API_KEY en settings)
    # Busca: "tipo negocio + ciudad", pagina resultados, extrae: nombre, teléfono, web, dirección, rating
    pass

class LinkedInScraper(BaseScraper):
    # Opción A: Apify/PhantomBuster via API (pago)
    # Opción B: Selenium/Playwright headless (frágil, solo dev)
    # Opción C: Export manual CSV desde Sales Navigator → subida Excel
    pass

class YellowPagesScraper(BaseScraper):
    # Scraping HTML de paginasamarillas.com.co / directorios locales
    pass

class ExcelImporter(BaseScraper):
    # Lee .xlsx/.csv con columnas: nombre, empresa, telefono, email, ciudad, notas
    # Normaliza teléfonos a wa_id (57 + 10 dígitos)
    pass
```

**Configuración en settings (.env):**
```
GOOGLE_PLACES_API_KEY=xxx
LINKEDIN_SCRAPER_API_URL=xxx  # si usas Apify
SCRAPER_DEFAULT_MAX_RESULTS=100
```

### 4.2 `outreach.py` — Motor de Campañas
```python
async def start_campaign(db, campaign_id: UUID) -> None:
    """Cambia status a 'active', calcula total_leads (leads new sin campaign_id asignados a esta campaña)."""

async def send_next_batch(db, campaign_id: UUID, channel: Channel) -> int:
    """Envía siguiente lote respetando:
    - daily_limit
    - allowed_hours (Colombia UTC-5)
    - min/max delay aleatorio entre envíos
    - Solo leads con status='new' y campaign_id asignado
    Returns: número de mensajes encolados/enviados.
    """

async def handle_inbound_reply(db, tenant_id: UUID, lead: Lead, message_text: str, channel: Channel) -> None:
    """Procesa respuesta del lead:
    1. Actualiza lead.status = 'replied', replied_at = now
    2. Llama a lead_qualification.qualify(db, lead, conversation_history)
    3. Si recommendation='handoff': notifica a tu WhatsApp (tenant.wa_id) + evento panel
    4. Si 'nurture': agenda follow-up en 3/7 días (OutreachMessage programado)
    5. Si 'discard' o 'opt_out': lead.status = 'closed_lost' / 'opt_out'
    """
```

### 4.3 `lead_qualification.py` — Calificación con IA (BANT)
```python
_QUALIFICATION_PROMPT = """
Eres Harvey, asistente de ventas de {bot_name}. Estás calificando un lead
para desarrollo de software / bots WhatsApp / agentes IA.

CONTEXTO DEL LEAD:
- Empresa: {company_name}
- Nombre: {full_name}
- Tu mensaje inicial: {outbound_message}
- Respuesta del lead: {reply_text}

EXTRAE (JSON):
{
  "budget": "tiene presupuesto confirmado | no mencionado | sin presupuesto",
  "authority": "es dueño | gerente | empleado | no claro",
  "need": "bot WhatsApp | agente IA | automatización | software a medida | no claro",
  "timeline": "inmediato | 1 mes | 3 meses | explorando | no mencionado",
  "summary": "2-3 líneas resumen",
  "recommendation": "handoff | nurture | discard",
  "confidence": 0.0-1.0
}

REGLAS:
- "handoff" = lead caliente: tiene necesidad clara + autoridad + timeline cercano
- "nurture" = interés pero sin timeline/autoridad claros → seguimiento en 7 días
- "discard" = no es prospecto (estudiante, vendedor, sin interés real)
- NUNCA alucines: si no dice presupuesto → "no mencionado"
"""

async def qualify(db, lead: Lead, conversation_history: list[Message]) -> LeadQualification:
    # Construye prompt, llama LLM (settings.llm_model), parsea JSON, guarda en lead.qualification
    # Actualiza lead.score (0-100) y lead.status según recommendation
    pass
```

### 4.4 `harvey_scheduler.py` — Job Diario (integrado en `main.py` lifespan)
```python
async def harvey_daily_job() -> None:
    """Corre cada 15 min en horario 8am-6pm Colombia (UTC 13:00-23:00).
    1. Para cada campaign active: send_next_batch()
    2. Procesa replies pendientes (leads con replied_at pero sin qualification)
    3. Envía follow-ups de nurture (3 y 7 días)
    4. Limpia leads opt_out / closed_lost antiguos (> 90 días)
    """
```

---

## 5. API Endpoints (`backend/app/api/v1/harvey.py`)

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/harvey/sources` | Lista fuentes configuradas |
| POST | `/harvey/sources` | Crea fuente (Maps query, LinkedIn, Excel upload) |
| POST | `/harvey/sources/{id}/run` | Ejecuta scraper (background task) |
| GET | `/harvey/sources/{id}/status` | Estado del scrape (progreso, logs) |
| GET | `/harvey/leads` | Lista leads con filtros: status, source, campaign, score_min, search (nombre/empresa) |
| GET | `/harvey/leads/{id}` | Detalle lead + historial mensajes + qualification |
| PATCH | `/harvey/leads/{id}` | Actualiza status, notes, asigna campaign |
| POST | `/harvey/leads/bulk-action` | Acción masiva: asignar campaign, cambiar status, exportar CSV |
| GET | `/harvey/campaigns` | Lista campañas |
| POST | `/harvey/campaigns` | Crea campaña (nombre, template, límites, horario) |
| PATCH | `/harvey/campaigns/{id}` | Actualiza campaña (pause/resume, editar template) |
| POST | `/harvey/campaigns/{id}/start` | Activa campaña (status=active) |
| GET | `/harvey/campaigns/{id}/stats` | Métricas: sent, delivered, read, replied, qualified, conversion rate |
| GET | `/harvey/dashboard/stats` | KPIs para tarjetas del panel: leads nuevos hoy, contactados, respondieron, calificados, en handoff |

**Auth:** Todos requieren `platform_admin` (User.is_platform_admin=True) — solo tú accedes.

---

## 6. Frontend — Panel Admin (`admin-web/src/pages/HarveyPage.tsx`)

### 6.1 Sidebar
```tsx
// En AppLayout.tsx, agregar al menú:
{ 
  label: "Harvey", 
  icon: <TargetIcon />, 
  href: "/harvey", 
  roles: ["platform_admin"]  // solo tú lo ves
}
```

### 6.2 Estructura de Rutas
```
/harvey                    → Dashboard (KPIs + pipeline resumen)
/harvey/sources            → Lista de fuentes + botón "Nueva fuente"
/harvey/sources/new        → Formulario: tipo (Maps/LinkedIn/Excel), config
/harvey/sources/:id        → Detalle fuente + logs de ejecución + leads encontrados
/harvey/leads              → Tabla/Kanban principal de leads (filtros, búsqueda, bulk actions)
/harvey/leads/:id          → Detalle lead: datos, conversación, qualification, botones (contactar, mover, nota)
/harvey/campaigns          → Lista campañas
/harvey/campaigns/new      → Formulario campaña (template con variables {nombre}, {empresa})
/harvey/campaigns/:id      → Detalle campaña + métricas + leads asignados
```

### 6.3 Componentes Clave

| Componente | Ubicación | Descripción |
|------------|-----------|-------------|
| `LeadTable` | `components/harvey/LeadTable.tsx` | Tabla virtualizada (tanstack/react-table): columnas seleccionables, filtros, ordenación, paginación |
| `LeadKanban` | `components/harvey/LeadKanban.tsx` | Vista Kanban drag-drop por status (new → contacted → replied → qualified → handoff → closed) |
| `LeadDetailDrawer` | `components/harvey/LeadDetailDrawer.tsx` | Panel lateral (Drawer) con tabs: Info, Conversación, Qualification, Historial |
| `SourceWizard` | `components/harvey/SourceWizard.tsx` | Wizard 3 pasos: Tipo → Config (query Maps / archivo Excel) → Confirmar |
| `CampaignForm` | `components/harvey/CampaignForm.tsx` | Form con editor de template (variables autocomplete), sliders para límites/horarios |
| `HarveyStatsCards` | `components/harvey/HarveyStatsCards.tsx` | 4-5 tarjetas KPI: Nuevos, Contactados, Respondieron, Calificados, En Handoff |

### 6.4 Estados de Lead (Pipeline) — Colores y Iconos
| Status | Label | Color | Icono | Acción principal |
|--------|-------|-------|-------|------------------|
| `new` | Nuevo | `gray` | `Plus` | Asignar campaña / Contactar |
| `contacted` | Contactado | `blue` | `Send` | Esperar respuesta |
| `replied` | Respondió | `amber` | `MessageCircle` | Calificar (IA) / Ver chat |
| `qualified` | Calificado | `green` | `CheckCircle` | Handoff → Tu WhatsApp |
| `handoff` | En mano | `purple` | `UserCheck` | Tú conversas y cierras |
| `closed_won` | Ganado | `emerald` | `Trophy` | Registrar proyecto |
| `closed_lost` | Perdido | `red` | `XCircle` | Motivo (precio, timing, etc.) |
| `opt_out` | No molestar | `slate` | `Ban` | Bloqueado permanentemente |

---

## 7. Flujo de Usuario (Tu Perspectiva)

```
1. ABRES /harvey/sources → "Nueva fuente" → Seleccionas "Google Maps"
   → Escribes query: "empresas de logística Medellín"
   → Max resultados: 100 → Guardar y Ejecutar

2. Harvey scrapea en background → ves progreso en /harvey/sources/:id
   → Al terminar: 47 leads importados (status=new)

3. ABRES /harvey/leads → Filtra: source="Google Maps", status="new"
   → Revisas: ves empresa, nombre, teléfono, dirección, rating
   → Seleccionas 20 buenos leads (checkbox) → "Asignar campaña"

4. ABRES /harvey/campaigns/new → Nombre: "Logística Medellín Oct"
   → Template: "Hola {nombre}, vi que {empresa} opera en Medellín...
     Ayudo a empresas como la tuya a automatizar pedidos/seguimiento
     por WhatsApp con bots a medida. ¿Te interesa una demo de 15 min?"
   → Límites: 15/día, 8am-6pm, delay 30-120s → Crear y Activar

5. Harvey (scheduler) envía 15 hoy, 15 mañana... en horario
   → Ves en /harvey/campaigns/:id → métricas en vivo

6. Lead RESPONDE por WhatsApp → webhook entrante
   → Harvey califica con IA → recommendation="handoff"
   → Lead.status = "qualified" → Notificación a TU WhatsApp:
     "🎯 Lead calificado: Logística SAS (Medellín) - necesita bot para
      seguimiento de entregas. Score: 85/100. Ver en panel."

7. ABRES /harvey/leads/:id → Ves qualification + conversación
   → Botón "Tomar conversación" → Abre WhatsApp Web / te da el número
   → Tú cierras el trato → Cambias status a "closed_won"
```

---

## 8. Seguridad y Cumplimiento

| Aspecto | Implementación |
|---------|----------------|
| **Ley 1581 (Habeas Data)** | Primer mensaje outbound incluye: "¿Te molesto si te cuento cómo ayudo a empresas como la tuya? Responde 'no' y no te escribo más." |
| **Opt-out automático** | Palabras clave: "no gracias", "borrame", "unsubscribe", "no me escribas" → `lead.status = 'opt_out'` + no más envíos |
| **Anti-ban WhatsApp** | Límite diario configurable (default 20), delays aleatorios 30-120s, horario 8am-6pm Colombia, `mark_read` + `send_typing` antes de responder |
| **Datos personales** | Solo nombre, empresa, teléfono, email de fuentes públicas + tu Excel. No se loguean conversaciones completas de leads no calificados. |
| **Acceso** | Solo `User.is_platform_admin=True` (tú). Middleware en API + ocultar en sidebar si no es platform_admin. |
| **Idempotencia** | `OutreachMessage.whatsapp_message_id` UNIQUE. `Lead` UNIQUE (tenant_id, phone). Dedupe en scraper e importación. |

---

## 9. Configuración (`.env` y `settings`)

```python
# backend/app/core/config.py — agregar a Settings
class Settings(BaseSettings):
    # ... existentes ...
    
    # Harvey / Scraping
    google_places_api_key: str | None = None
    linkedin_scraper_api_url: str | None = None  # Apify/PhantomBuster
    harvey_default_daily_limit: int = 20
    harvey_allowed_hours_start: int = 8   # Colombia UTC-5
    harvey_allowed_hours_end: int = 18
    harvey_min_delay_seconds: int = 30
    harvey_max_delay_seconds: int = 120
    
    # LLM para calificación (usa el mismo que el asistente)
    # llm_model, llm_api_key, llm_base_url ya existen
```

---

## 10. Migraciones Alembic

```bash
# backend/alembic/versions/xxxx_add_harvey_models.py
# Tablas: lead_sources, leads, outreach_campaigns, outreach_messages
# Índices: lead.status, lead.source_id, lead.campaign_id, lead.score
#           outreach_message.campaign_id, outreach_message.lead_id
#           outreach_message.whatsapp_message_id (UNIQUE)
```

---

## 11. Testing Mínimo

| Qué | Cómo |
|-----|------|
| Scraper Maps | Mock `googlemaps.Client` → devuelve places ficticios → verifica `LeadCreate` correctos |
| Excel Import | Archivo .xlsx fixture → verifica normalización teléfonos, deduplicación |
| Outreach Engine | Campaign con 3 leads mock → `send_next_batch` respeta daily_limit, horario, delays |
| Calificación IA | Mock `AsyncOpenAI` → respuesta JSON BANT fija → verifica `lead.qualification` guardado |
| API Endpoints | `TestClient` + auth platform_admin → 200/403 correctos |
| Frontend | Render `HarveyPage` → tabs navegan, tabla carga, drawer abre, formularios validan |

---

## 12. Riesgos y Mitigaciones

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|--------------|---------|------------|
| Ban de WhatsApp (Evolution/Baileys) | Media | Alto | Límites conservadores, migración a Cloud API oficial en Fase 2 |
| Scrapers frágiles (selectores cambian) | Alta | Medio | Scrapers como plugins; fallback a Excel upload; logging detallado |
| Falsos positivos en calificación IA | Media | Medio | `confidence` threshold; revisión manual antes de handoff; feedback loop |
| Leads duplicados (mismo teléfono en varias fuentes) | Alta | Bajo | UNIQUE constraint + merge logic en importer |
| Costos LLM en calificación masiva | Baja | Medio | Cache de qualification por lead; batch processing; modelo barato (Haiku) |

---

## 13. Fases de Implementación Sugeridas

| Fase | Entregable | Esfuerzo |
|------|------------|----------|
| **1. Backend Core** | Modelos, migraciones, servicios (scraper base, outreach, qualification), API CRUD | ~3-4 días |
| **2. Scrapers Reales** | GoogleMapsScraper funcional, ExcelImporter, stubs LinkedIn/YellowPages | ~2-3 días |
| **3. Scheduler + IA** | Job diario en `main.py`, calificación BANT real, notificaciones a tu WhatsApp | ~2 días |
| **4. Frontend Panel** | Sidebar, Dashboard, Sources, Leads (Tabla+Kanban), Campaigns, Detalle Lead | ~4-5 días |
| **5. Pulido + Tests** | E2E manual, edge cases, anti-ban tuning, documentación | ~2 días |

**Total estimado:** ~13-16 días de trabajo enfocado.

---

## 14. Decisiones Técnicas Clave (ADR)

| Decisión | Alternativa Descartada | Justificación |
|----------|------------------------|---------------|
| Harvey en tenant de plataforma (no tenant propio) | Tenant separado "harvey-sales" | Reusa infra auth, canal, LLM, BD. Aislamiento por `tenant_id` ya existe. |
| Scrapers como servicios Python (no workers externos) | Apify/Browserless vía webhook | Control total, sin costos recurrentes, debug local fácil. Cloud API opcional después. |
| Calificación IA síncrona en webhook | Cola async (ARQ/Celery) | Volumen bajo (<50 replies/día); simplicidad. Migrar a worker si escala. |
| Kanban + Tabla (dos vistas) | Solo tabla | Kanban para pipeline visual; tabla para bulk actions y filtros complejos. |
| Template con variables `{nombre}`, `{empresa}` | Jinja2 completo | Simple, seguro (no ejecución de código), suficiente para personalización. |

---

## 15. Próximos Pasos

1. ✅ Spec aprobada (este documento)
2. 📋 **Plan de implementación** → invocar `writing-plans` skill
3. 🏗️ Ejecutar fases 1-5 en orden
4. 🚀 Deploy a staging → prueba real con 10-20 leads tuyos
5. 📈 Iterar: afinar template, scoring, scrapers

---

**Firmado:** _________________ (Juan David) — 2026-10-28