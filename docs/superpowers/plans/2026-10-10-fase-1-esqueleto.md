# Fase 1 — Esqueleto de punta a punta: plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Meta:** construir el esqueleto funcionando de punta a punta: docker-compose (Postgres/pgvector + Redis), backend FastAPI con 10 tablas (todas con `tenant_id` salvo `tenants`), auth JWT, webhook de WhatsApp idempotente que publica eventos en Redis, capa de canal abstracta con stub de Evolution, WebSocket `/ws/events`, seed de tenant + admin, panel React (Login + Dashboard con feed en vivo) y tests.

**Arquitectura:** monolito modular FastAPI con API versionada `/api/v1`; SQLAlchemy 2.x async + psycopg 3; Redis solo como pub/sub de eventos (sin ARQ en F1); WebSocket autenticado por JWT que reenvía los eventos del canal del tenant; frontend Vite/React/TS con shadcn/ui.

**Tech Stack:** Python 3.12 (venv en `backend/.venv`), FastAPI, SQLAlchemy 2.x async, psycopg[binary] 3, Alembic, Pydantic v2 + pydantic-settings, PyJWT, bcrypt, redis-py (asyncio); React + Vite + TypeScript + Tailwind v4 + shadcn/ui + TanStack Query + react-router; PostgreSQL 16 con pgvector y Redis 7 (docker-compose ya existente).

**Spec:** `docs/FASES.md` (sección Fase 1 — prompt exacto de 8 ítems + requisitos de verificación) y `CLAUDE.md` (rol, reglas de arquitectura, stack, estructura, comandos).

## Hallazgos previos que condicionan el plan

- **`.env.example` está ignorado** por la regla `.env.*` de `.gitignore` → la Tarea 0 añade `!.env.example`; sin eso la plantilla nunca entra al repo.
- `docker-compose.yml` **ya existe** (creado por otro agente, cumple la spec: `pgvector/pgvector:pg16` + `redis:7-alpine`, healthchecks, volúmenes) → se reutiliza tal cual. **OJO OneDrive:** durante la revisión adversarial el archivo parpadeó a 0 bytes y volvió — T0 valida con `docker compose config --quiet` antes de levantar servicios; si vuelve a quedar vacío, restaurar con `git show 0690737:docker-compose.yml > docker-compose.yml`.
- `docs/MODULOS.md` tiene cambios locales en el árbol de trabajo → el commit de fase usa `git add` con **lista explícita** (nunca `-A`) y lo excluye.
- `core.autocrlf=true` global; todos los pasos asumen PowerShell y ejecución desde `backend/` salvo indicación contraria.

## Restricciones globales (aplican a toda tarea)

- Código en inglés; textos de UI en español; type hints en todo el Python; `ruff check .` limpio.
- **Todas las tablas llevan `tenant_id`** (FK a `tenants.id` con `ondelete="CASCADE"`) salvo `tenants`.
- API versionada bajo `/api/v1`; los webhooks responden 200 de inmediato; **idempotencia** por `(tenant_id, whatsapp_message_id)`.
- Alcance ESTRICTO a los 8 ítems del prompt de Fase 1: **sin tabla memories, sin worker ARQ, sin IA, sin PDFs, sin Dockerfile, sin deploy**.
- Un solo commit al final de la fase (FASES.md: "Un commit por fase"), mensaje Conventional Commits.
- `tenants.bot_name` con default `'Aura'`; seed no interactivo con flag opcional.

## Review Focus (entradas que el spec implica y cada test ancla)

1. Webhook duplicado (mismo `whatsapp_message_id`) → 200 ambas veces, UNA fila en `messages` y en `events` → T11.
2. Payload malformado / sin texto extraíble → 400 sin crash → T9 + T11.
3. `X-Tenant-Slug` desconocido o tenant inactivo → 404 sin filtrar información → T11.
4. Password incorrecta vs email inexistente → mismo 401, sin revelar cuál falló → T7.
5. Redis caído durante el webhook → el request sigue 200 y el mensaje queda persistido → T11 (monkeypatch).
6. Token inválido/expirado → 401 en API (T6/T8) y cierre 1008 en WS (verificación manual G.13).

---

## A. Estructura de archivos

### Raíz

| Archivo | Acción | Responsabilidad |
|---|---|---|
| `.gitignore` | M | Añadir `!.env.example` justo después de `.env.*` |
| `.env.example` | M (rellenar) | `POSTGRES_USER/PASSWORD/DB`, `DATABASE_URL`, `REDIS_URL`, `JWT_SECRET` (placeholder no-secreto) |
| `.env` | Crear (NO commit) | Copia local con `JWT_SECRET` real (generar con `python -c "import secrets; print(secrets.token_urlsafe(48))"`) |
| `README.md` | M | Descripción real + comandos de puesta en marcha y desarrollo |
| `docker-compose.yml` | Sin cambios (trackear) | Ya correcto |

Contenido exacto de `.env.example`:

```
POSTGRES_USER=asistente
POSTGRES_PASSWORD=asistente
POSTGRES_DB=asistente
DATABASE_URL=postgresql+psycopg_async://asistente:asistente@localhost:5432/asistente
REDIS_URL=redis://localhost:6379/0
JWT_SECRET=cambia-esto-por-una-cadena-larga-y-aleatoria
```

### backend/

```
backend/
├── requirements.txt            # deps runtime
├── requirements-dev.txt        # pytest, pytest-asyncio, httpx, ruff
├── pyproject.toml              # SOLO [tool.*]: ruff y pytest (no es paquete instalable)
├── alembic.ini                 # script_location=alembic; sqlalchemy.url VACÍA (la pone env.py)
├── alembic/
│   ├── env.py                  # M: engine async desde Settings; target_metadata = Base.metadata
│   ├── script.py.mako          # generado por alembic init
│   └── versions/<rev>_create_base_tables.py   # migración inicial (autogenerada + revisada a mano)
├── scripts/
│   ├── __init__.py
│   └── create_admin.py         # seed no interactivo: tenant + admin (argparse + getpass)
├── app/
│   ├── __init__.py
│   ├── main.py                 # app FastAPI; GET /health; monta api_router y el websocket
│   ├── core/
│   │   ├── config.py           # Settings (pydantic-settings) + get_settings() con lru_cache
│   │   ├── database.py         # async engine + SessionFactory + dependencia get_db
│   │   ├── redis.py            # get_redis(): cliente redis.asyncio por request
│   │   └── security.py         # bcrypt hash/verify + JWT HS256 create/decode
│   ├── models/                 # base.py (Base+naming+TimestampMixin) + 10 modelos, __init__ importa todo
│   ├── schemas/
│   │   ├── auth.py             # LoginRequest, UserPublic, LoginResponse
│   │   ├── channel.py          # IncomingMessage
│   │   ├── events.py           # EventOut
│   │   └── webhook.py          # WebhookAck
│   ├── channels/
│   │   ├── __init__.py         # registro get_channel(name) -> Channel
│   │   ├── base.py             # Channel(ABC) + ChannelParseError
│   │   └── evolution.py        # EvolutionChannel: parse del payload; send_text = no-op con log
│   ├── services/
│   │   ├── events.py           # events_channel(tenant_id) + publish_event(...)
│   │   └── messages.py         # ingest_message(): parse → dedupe → persistir → IngestResult
│   ├── api/
│   │   ├── deps.py             # oauth2_scheme, get_current_user, require_role, get_tenant_by_slug
│   │   ├── ws.py               # /ws/events: JWT por query param + suscripción pub/sub Redis
│   │   └── v1/
│   │       ├── __init__.py     # api_router = APIRouter(prefix="/api/v1")
│   │       ├── auth.py         # POST /auth/login
│   │       └── webhooks.py     # POST /webhooks/whatsapp
└── tests/
    ├── conftest.py             # JWT_SECRET test, BD asistente_test, fixtures
    ├── test_health.py          # GET /health
    ├── test_fixtures.py        # persistencia + aislamiento
    ├── test_security.py        # bcrypt + JWT
    ├── test_deps.py            # get_current_user, require_role
    ├── test_auth.py            # login ok / 401
    ├── test_channel_evolution.py
    ├── test_webhook.py         # idempotencia + errores
    └── test_create_admin.py    # seed
```

Nota: el WebSocket vive en `app/api/ws.py` (la estructura de CLAUDE.md lista `api/`, sin carpeta `ws/`).

### admin-web/

```
admin-web/
├── index.html
├── package.json
├── vite.config.ts          # react + tailwindcss; alias "@"→src; proxy /api (http) y /ws (ws:true) → :8000
├── tsconfig*.json + components.json   # plantilla Vite + shadcn init
└── src/
    ├── main.tsx            # QueryClientProvider + BrowserRouter + AuthProvider
    ├── App.tsx             # rutas: /login y / (protegida)
    ├── index.css           # @import "tailwindcss" + tokens shadcn
    ├── types.ts            # User, LoginResponse, FeedEvent, WsStatus
    ├── lib/{api.ts,ws.ts} # apiFetch con bearer; buildWsUrl(token)
    ├── auth/{AuthContext.tsx,ProtectedRoute.tsx}
    ├── hooks/{useLogin.ts,useEvents.ts}
    ├── components/{ui/*,MessageFeed.tsx}
    └── pages/{LoginPage.tsx,DashboardPage.tsx}
```

---

## B. Esquema de las 10 tablas

`app/models/base.py`: `Base(DeclarativeBase)` con `MetaData(naming_convention=...)` (ix/uq/ck/fk/pk) y `TimestampMixin` (`created_at`/`updated_at` = `DateTime(timezone=True)`, `server_default=func.now()`, `onupdate=func.now()`). PK `id` tipo `Uuid` con `default=uuid.uuid4`. `events.payload` = `JSONB`. Monedas `Numeric(12,2)`. Regla: toda columna FK lleva índice; `tenant_id` queda cubierto cuando es columna inicial de un UNIQUE o índice compuesto.

1. **tenants** (sin tenant_id): `name` VARCHAR(100) NOT NULL; `slug` VARCHAR(50) NOT NULL **UNIQUE**; `bot_name` VARCHAR(50) NOT NULL **DEFAULT 'Aura'** (server_default); `is_active` BOOLEAN NOT NULL DEFAULT TRUE.
2. **users**: `tenant_id` FK CASCADE (cubierto por uq); `email` VARCHAR(255); `password_hash` VARCHAR(255); `full_name` VARCHAR(100) NULL; `role` VARCHAR(20) DEFAULT 'admin' CHECK `role IN ('admin','user')`; `is_active` DEFAULT TRUE; **UNIQUE (tenant_id, email)**.
3. **contacts**: `tenant_id` (cubierto por uq); `wa_id` VARCHAR(50) (teléfono, solo dígitos); `name` VARCHAR(100) NULL; **UNIQUE (tenant_id, wa_id)**.
4. **conversations**: `tenant_id`; `contact_id` FK CASCADE (índice explícito); `status` DEFAULT 'open' CHECK `IN ('open','closed')`; `last_message_at` TIMESTAMPTZ NULL; `Index("ix_conversations_tenant_last_message_at", tenant_id, last_message_at)`.
5. **messages**: `tenant_id` (cubierto por uq); `conversation_id` FK CASCADE (índice); `direction` CHECK `IN ('in','out')`; `type` DEFAULT 'text' CHECK `IN ('text','audio','image','document')`; `content` TEXT NULL; `whatsapp_message_id` VARCHAR(255) NOT NULL; `status` DEFAULT 'received'; **UNIQUE (tenant_id, whatsapp_message_id)** ← clave de idempotencia; `Index("ix_messages_tenant_created", tenant_id, created_at)`.
6. **catalog_items**: `tenant_id` (cubierto por uq); `name` VARCHAR(200); `description` TEXT NULL; `unit` VARCHAR(50); `unit_price` Numeric(12,2) CHECK >= 0; `is_active` DEFAULT TRUE; **UNIQUE (tenant_id, name)**.
7. **quotes**: `tenant_id`; `conversation_id` FK **SET NULL** (índice); `contact_id` FK **SET NULL** (índice); `status` DEFAULT 'draft' CHECK `IN ('draft','sent','accepted','rejected','expired')`; `total` Numeric(12,2) DEFAULT 0 CHECK >= 0; `notes` TEXT NULL; `valid_until` TIMESTAMPTZ NULL; `Index("ix_quotes_tenant_status", tenant_id, status)`.
8. **quote_items**: `tenant_id` (índice); `quote_id` FK CASCADE (índice); `catalog_item_id` FK **SET NULL** (índice); `description` VARCHAR(200); `quantity` Numeric(10,2) DEFAULT 1 CHECK > 0; `unit_price` Numeric(12,2) CHECK >= 0; `line_total` DEFAULT 0; `position` INTEGER DEFAULT 0.
9. **events**: `tenant_id` (cubierto por ix); `type` VARCHAR(50) (F1 solo `"message.received"`); `payload` JSONB NOT NULL DEFAULT '{}'; `Index("ix_events_tenant_created", tenant_id, created_at)`. Append-only.
10. **llm_usage**: `tenant_id` (cubierto por ix); `conversation_id` FK **SET NULL** (índice); `model` VARCHAR(100); `purpose` VARCHAR(100) NULL; `input_tokens`/`output_tokens` INTEGER DEFAULT 0; `audio_seconds` Numeric(10,2) NULL; `Index("ix_llm_usage_tenant_created", tenant_id, created_at)`. F1 solo crea la tabla.

Migración única (workflow del skill `db-migration`): `alembic revision --autogenerate -m "create base tables"` contra BD vacía → revisar a mano índices/uniques/checks/defaults/downgrade → `alembic upgrade head`.

---

## C. Contratos de endpoints

### GET /health (sin auth)
`200` → `{"status": "ok"}` (sin tocar BD/Redis: determinista para tests).

### POST /api/v1/auth/login
Request: `{"email": "admin@example.com", "password": "Admin1234!"}`
Response `200`:
```json
{"access_token": "eyJ...", "token_type": "bearer",
 "user": {"id": "<uuid>", "email": "admin@example.com", "full_name": null,
          "role": "admin", "tenant_id": "<uuid>", "bot_name": "Aura"}}
```
Errores: `401 {"detail": "Credenciales inválidas"}` (password mal o email inexistente, mismo mensaje); `400 {"detail": "El correo pertenece a varios tenants"}` (colisión de email entre tenants); `422` body malformado.
JWT: HS256 con `JWT_SECRET`, `exp = iat + 1440 min`; claims `{"sub": "<user uuid>", "tenant_id": "<uuid>", "role": "admin"}`.

### POST /api/v1/webhooks/whatsapp
Headers: `X-Tenant-Slug: personal` (requerido). Body (estilo Evolution):
```json
{"event": "messages.upsert", "instance": "auratest",
 "data": {"key": {"id": "3EB0F9B1B5D6C7D8", "remoteJid": "573001234567@s.whatsapp.net", "fromMe": false},
          "pushName": "Juan Pérez", "messageType": "conversation",
          "message": {"conversation": "Hola, necesito una cotización para un tablero"},
          "status": "RECEIVED"}}
```
Response `200` (siempre, incluidos duplicados): `{"status": "ok", "whatsapp_message_id": "...", "duplicate": false}`. El duplicado no republica evento: sigue habiendo UNA fila en `messages` y UNA en `events`.
Errores: `404 {"detail": "Tenant no encontrado"}` (slug desconocido o inactivo); `400 {"detail": "Payload de webhook inválido"}` (falta `data.key.id`, `remoteJid` o texto extraíble).
Deuda consciente (F3): sin verificación de firma del webhook; F1 es local-only.

### Dependencias (`app/api/deps.py`)

```python
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)],
                           db: Annotated[AsyncSession, Depends(get_db)]) -> User
    # token inválido → 401 "Token inválido o expirado"; sub no uuid / user None / inactivo → 401 "Usuario no válido"

def require_role(*roles: str) -> Callable[..., User]
    # user.role not in roles → 403 "Permisos insuficientes"

async def get_tenant_by_slug(x_tenant_slug: Annotated[str, Header(alias="X-Tenant-Slug")],
                             db: Annotated[AsyncSession, Depends(get_db)]) -> Tenant
    # slug desconocido o inactivo → 404 "Tenant no encontrado"
```

---

## D. Capa de canal

`app/channels/base.py`:

```python
class ChannelParseError(Exception): ...

class Channel(ABC):
    name: ClassVar[str]

    @abstractmethod
    async def parse_incoming(self, payload: dict[str, Any]) -> IncomingMessage: ...

    @abstractmethod
    async def send_text(self, to: str, text: str) -> None: ...
```

`app/schemas/channel.py`:

```python
class IncomingMessage(BaseModel):
    channel_message_id: str          # WhatsApp message id (clave de dedupe)
    wa_id: str                       # teléfono del remitente, solo dígitos
    push_name: str | None = None
    message_type: Literal["text", "audio", "image", "document"] = "text"
    text: str | None = None          # solo para message_type == "text"
    raw: dict[str, Any] = Field(default_factory=dict)
```

`app/channels/evolution.py` — `EvolutionChannel`, `name = "evolution"`. `parse_incoming`: `channel_message_id = payload["data"]["key"]["id"]`; `wa_id = payload["data"]["key"]["remoteJid"].split("@", 1)[0]`; `text = message.conversation or message.extendedTextMessage.text`; falta algo → `ChannelParseError`. `send_text`: stub — `logger.info(...)` y retorna.

`app/channels/__init__.py`: `_CHANNELS = {"evolution": EvolutionChannel}` + `get_channel(name) -> Channel` (desconocido → ValueError). El webhook usa `get_channel("evolution")`.

`app/services/messages.py`:

```python
class IngestResult(NamedTuple):
    message: Message
    event: Event | None
    created: bool

async def ingest_message(db: AsyncSession, tenant: Tenant,
                         channel: Channel, payload: dict[str, Any]) -> IngestResult
```

Pasos: (1) `parse_incoming` (error → 400 en el endpoint). (2) dedupe por `(tenant_id, whatsapp_message_id)` → existe → `(msg, None, False)`. (3) get-or-create Contact por `(tenant_id, wa_id)` (rellena `name` con push_name si era NULL). (4) get-or-create Conversation (la más reciente del contacto; si no hay → `status="open"`); actualizar `last_message_at`. (5) insert Message (`direction="in"`). (6) insert Event `type="message.received"` con payload de valores serializables (UUIDs como `str()`): `{"message_id": str(message.id), "conversation_id": str(conv.id), "contact_id": str(contact.id), "contact_wa_id": incoming.wa_id, "push_name": incoming.push_name, "direction": "in", "preview": (incoming.text or "")[:120] or None}` — psycopg no serializa UUID en JSONB. (7) `commit()`; `IntegrityError` (carrera del UNIQUE) → rollback + re-consultar → `(existente, None, False)`. (8) refresh → `(message, event, True)`.

`app/services/events.py`:

```python
def events_channel(tenant_id: uuid.UUID | str) -> str          # "events:{tenant_id}"
async def publish_event(client: Redis, tenant_id: uuid.UUID, event: Event) -> None
    # EventOut(...).model_dump_json() → client.publish(events_channel(tenant_id), body)
```

`app/schemas/events.py`:

```python
class EventOut(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    type: str
    created_at: datetime
    data: dict[str, Any]      # = event.payload
```

---

## E. Protocolo del WebSocket /ws/events

- URL: `ws://localhost:8000/ws/events?token=<JWT>` (en dev el navegador usa el proxy de Vite).
- Handshake: con token ausente/inválido/expirado o usuario inactivo → `await websocket.accept()` seguido de `await websocket.close(code=1008)` **sin enviar la trama `connected`**. (Cerrar antes de accept solo produce un HTTP 403: el navegador reporta 1006 y el 1008 nunca llega — logout imposible.) Con token válido: cargar User por `sub`, verificar `is_active`.
- Primera trama tras accept: `{"type": "connected", "tenant_id": "<uuid>", "bot_name": "Aura"}`.
- Eventos: cada mensaje del canal Redis `events:{tenant_id}` (el del usuario) se reenvía verbatim: `{"id": "...", "type": "message.received", "tenant_id": "...", "created_at": "...", "data": {...}}`.
- Cliente → servidor: nada; el endpoint solo lee para detectar desconexión.
- Aislamiento: cada socket se suscribe únicamente al canal de su tenant.
- Frontend: close 1008 → logout y a `/login`; otro cierre → reintentar en 2 s.

---

## F. Tareas en orden (TDD)

Convención: venv activado desde `backend/` (`.venv\Scripts\Activate.ps1`; si PowerShell lo bloquea, invocar `.\.venv\Scripts\python.exe -m pytest` y `.\.venv\Scripts\alembic.exe` directamente). Requisito global: Docker Desktop corriendo.

### Task 0: Higiene de repo y entorno
- [ ] `.gitignore`: añadir `!.env.example` tras `.env.*`
- [ ] `.env.example` con el contenido exacto de la sección A; crear `.env` local con `JWT_SECRET` real
- [ ] `docker compose config --quiet` (valida que el archivo no esté truncado por OneDrive; si falla: restaurar del checkpoint `0690737`)
- [ ] `docker compose up -d` → `docker compose ps` muestra ambos servicios `running (healthy)`

### Task 1: Esqueleto backend + GET /health
**Crea:** `requirements.txt` (`fastapi>=0.115,<1.0`, `uvicorn[standard]>=0.30,<1.0`, `pydantic[email]>=2.8,<3.0`, `pydantic-settings>=2.4,<3.0`, `sqlalchemy[asyncio]>=2.0.30,<2.1`, `psycopg[binary]>=3.2,<4.0`, `alembic>=1.13,<2.0`, `redis>=5.0,<7.0`, `pyjwt>=2.8,<3.0`, `bcrypt>=4.1,<5.0`), `requirements-dev.txt` (`pytest>=8.2,<9.0`, `pytest-asyncio>=0.26,<1.0`, `httpx>=0.27,<1.0`, `ruff>=0.6`), `pyproject.toml` (`[tool.ruff] line-length=100, target-version="py312"`; `[tool.ruff.lint] select=["E","F","I","UP","B"]`; `[tool.pytest.ini_options] asyncio_mode="auto"`, `asyncio_default_fixture_loop_scope="session"`, `asyncio_default_test_loop_scope="session"`, `testpaths=["tests"]`), `app/main.py`, `app/__init__.py`, `app/api/__init__.py`, `app/api/v1/__init__.py`, `tests/__init__.py`, `tests/conftest.py` (v1: `os.environ.setdefault("JWT_SECRET", "test-secret")` + fixture `client` con `AsyncClient(transport=ASGITransport(app=app), base_url="http://test")`), `tests/test_health.py`.
- [ ] venv + `pip install -r requirements.txt -r requirements-dev.txt`
- [ ] RED: `test_health.py` → `assert r.status_code == 200` y `r.json() == {"status": "ok"}` → falla
- [ ] VERDE: `main.py` con `app = FastAPI(title="Asistente Personal API")` + `GET /health` → `pytest` 1 passed

### Task 2: Configuración core
**Crea:** `app/core/{__init__,config,database,redis}.py`.
**Interfaces:**
```python
# config.py — _ENV_FILE = Path(__file__).resolve().parents[3] / ".env"  (raíz del repo)
class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg_async://asistente:asistente@localhost:5432/asistente"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str                      # SIN default → fail-fast
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440
    model_config = SettingsConfigDict(env_file=str(_ENV_FILE), env_file_encoding="utf-8", extra="ignore")

@lru_cache
def get_settings() -> Settings: ...

# database.py
engine: Final[AsyncEngine] = create_async_engine(get_settings().database_url, pool_pre_ping=True)
SessionFactory: Final[async_sessionmaker[AsyncSession]] = async_sessionmaker(engine, expire_on_commit=False)
async def get_db() -> AsyncIterator[AsyncSession]: ...

# redis.py
async def get_redis() -> AsyncIterator[Redis]:   # Redis.from_url(..., decode_responses=True) → yield → aclose()
```
- [ ] Smoke: `python -c "from app.core.config import get_settings; print(get_settings().database_url)"` imprime la URL; `python -c "from app.core.database import engine"` sin error

### Task 3: Modelos: 10 tablas
**Crea:** `app/models/` completo (sección B).
- [ ] `python -c "from app.models import Base; print(sorted(Base.metadata.tables))"` → imprime exactamente las 10

### Task 4: Alembic + migración inicial (skill `db-migration`)
- [ ] `alembic init -t async alembic` desde `backend/`; M `env.py` (importar `get_settings` y `app.models`; `config.set_main_option("sqlalchemy.url", get_settings().database_url)`); M `alembic.ini` (url vacía)
- [ ] `alembic revision --autogenerate -m "create base tables"` → revisar a mano índices/uniques/checks/defaults/downgrade
- [ ] `alembic upgrade head` → `docker exec asistente_postgres psql -U asistente -d asistente -c "\dt"` → 10 tablas + `alembic_version`
- [ ] `alembic downgrade -1` (0 tablas) → `alembic upgrade head` (10 tablas)

### Task 5: Fixtures de test: BD `asistente_test`
**Modifica:** `tests/conftest.py`. **Crea:** `tests/test_fixtures.py`.
**Interfaces:**
```python
@pytest_asyncio.fixture(scope="session")
async def test_engine() -> AsyncIterator[AsyncEngine]:
    # 1) engine admin a BD "postgres" con isolation_level="AUTOCOMMIT" (psycopg: CREATE DATABASE fuera de transacción)
    #    URL: make_url(get_settings().database_url).set(database="postgres")
    # 2) DROP DATABASE IF EXISTS asistente_test; CREATE DATABASE asistente_test  (exec_driver_sql)
    # 3) engine de test → 4) create_all → yield → dispose()

@pytest_asyncio.fixture
async def db_session(test_engine) -> AsyncIterator[AsyncSession]:
    # TRUNCATE de todas: ", ".join(reversed(Base.metadata.sorted_tables)) → "TRUNCATE TABLE ... RESTART IDENTITY CASCADE"

@pytest_asyncio.fixture
async def client(db_session) -> AsyncClient:   # dependency_overrides[get_db]

@pytest_asyncio.fixture
async def tenant(db_session) -> Tenant          # name="Personal", slug="personal", bot_name="Aura"
@pytest_asyncio.fixture
async def admin_user(db_session, tenant) -> User  # email="admin@example.com", hash de "Admin1234!", role="admin"
```
- [ ] RED: insertar Tenant y contar → 1; segundo test cuenta Tenants → 0 (aislamiento por TRUNCATE)
- [ ] VERDE al implementar; regresión: `test_health` sigue en verde

### Task 6: bcrypt + JWT (unitario)
**Crea:** `app/core/security.py`, `tests/test_security.py`.
**Interfaces:**
```python
def hash_password(password: str) -> str: ...
def verify_password(plain_password: str, password_hash: str) -> bool: ...
def create_access_token(user_id: uuid.UUID, tenant_id: uuid.UUID, role: str,
                        expires_delta: timedelta | None = None) -> str: ...
def decode_access_token(token: str) -> dict[str, Any]: ...   # raises jwt.InvalidTokenError
```
- [ ] RED: (1) verify(hash("Admin1234!")) is True; (2) password distinta → False; (3) decode(create(...)) → claims sub/tenant_id/role; (4) `expires_delta=timedelta(seconds=-1)` → `pytest.raises(jwt.InvalidTokenError)`
- [ ] VERDE

### Task 7: POST /api/v1/auth/login
**Crea:** `app/schemas/{__init__,auth}.py`, `app/api/v1/auth.py`, `tests/test_auth.py`. **Modifica:** `app/api/v1/__init__.py` (componer `api_router`), `app/main.py` (montarlo).
**Interfaces:** `LoginRequest(email: EmailStr, password: str)`; `UserPublic(id, email, full_name, role, tenant_id, bot_name)`; `LoginResponse(access_token, token_type="bearer", user: UserPublic)`.
- [ ] RED: (1) login con `admin_user` → 200, `decode_access_token(...)` con sub==user.id, role=="admin", `body["user"]["bot_name"] == "Aura"`; (2) password "wrong" → 401; (3) email fantasma → 401 (mismo mensaje que (2))
- [ ] VERDE: select por email (0 → 401; >1 → 400); `verify_password` + `is_active` → 401 uniforme

### Task 8: deps de auth (unitario)
**Crea:** `app/api/deps.py`, `tests/test_deps.py`.
- [ ] RED: (1) `get_current_user(token=..., db=db_session)` devuelve admin_user; (2) token "no-es-jwt" → HTTPException 401; (3) `require_role("admin")` acepta; (4) role "user" → HTTPException 403
- [ ] VERDE (invocando las dependencias directamente, sin endpoints nuevos)

### Task 9: Capa de canal (unitario)
**Crea:** `app/schemas/channel.py`, `app/channels/{__init__,base,evolution}.py`, `tests/test_channel_evolution.py`. Payload de ejemplo en conftest como `EVOLUTION_TEXT_PAYLOAD`.
- [ ] RED: (1) parse con `conversation` → IncomingMessage con id/wa_id/push_name/text/raw correctos; (2) variante `extendedTextMessage.text`; (3) sin `data.key.id` → ChannelParseError; (4) `send_text` retorna None sin error
- [ ] VERDE

### Task 10: Publicador de eventos
**Crea:** `app/schemas/events.py`, `app/services/{__init__,events}.py`. Interfaces: sección D. (Sin test propio; lo ejercen T11 y la verificación manual G.)

### Task 11: Webhook idempotente (integración)
**Crea:** `app/services/messages.py`, `app/schemas/webhook.py`, `app/api/v1/webhooks.py`, `tests/test_webhook.py`. **Modifica:** `app/api/v1/__init__.py`.
**Interfaces:** `WebhookAck(status="ok", whatsapp_message_id: str, duplicate: bool = False)`; `ingest_message(...)`; ruta `@router.post("/webhooks/whatsapp", response_model=WebhookAck)` con `tenant: Depends(get_tenant_by_slug)`, `db: Depends(get_db)`, `redis_client: Depends(get_redis)`.
- [ ] RED: (1) **idempotencia (spec)**: dos POST idénticos → ambos 200, primero `duplicate=False`, segundo `True`; `count(*) messages == 1` y `count(*) events == 1`; (2) slug "nope" → 404; (3) payload sin `data.key.id` → 400; (4) **Redis caído**: monkeypatch de `publish_event` que lanza RuntimeError → el POST sigue 200 y la fila existe
- [ ] VERDE: `ingest_message` + endpoint; `ChannelParseError` → 400; si `created`: `publish_event` en `try/except Exception: logger.exception(...)` (Redis caído NO rompe el 200)

### Task 12: WebSocket /ws/events (verificación manual)
**Crea:** `app/api/ws.py`. **Modifica:** `app/main.py` (montar el router).
**Interfaz:** `router = APIRouter()` + `@router.websocket("/ws/events")` → `events_socket(websocket: WebSocket, db: Annotated[AsyncSession, Depends(get_db)]) -> None` con el protocolo de la sección E.
- [ ] Auth: token ausente/inválido/expirado o usuario inactivo → `accept()` + `close(1008)` sin enviar `connected` (cerrar antes de accept entrega un 403 que el navegador ve como 1006)
- [ ] Implementación: `pubsub` de `redis.asyncio` (cliente por conexión), `subscribe(events_channel(user.tenant_id))`, bucle `get_message(ignore_subscribe_messages=True, timeout=1.0)` → `websocket.send_text(...)`; `finally`: cancelar tarea lectora, unsubscribe, `aclose()`, cerrar sesión DB
- [ ] Sin test automatizado (httpx no soporta WS; TestClient síncrono rompe con psycopg async): se verifica en G.13 y en el E2E de T16

### Task 13: Seed script
**Crea:** `scripts/{__init__,create_admin}.py`, `tests/test_create_admin.py`.
**Interfaces:**
```python
def slugify(value: str) -> str
async def run(tenant_name: str, bot_name: str, slug: str, email: str, password: str,
             session_factory: async_sessionmaker[AsyncSession] | None = None) -> dict
# → {"tenant_id": ..., "tenant_slug": ..., "user_id": ...}; crea tenant (reusa si existe);
#   usuario (tenant, email) ya existe → raise SystemExit(1)
def main() -> None   # argparse: --tenant-name (default "Personal"), --bot-name (default "Aura"),
                     # --slug (default slugify(tenant_name)), --email (required), --password (getpass si falta)
```
- [ ] RED (con `session_factory` a `asistente_test`): (1) crea tenant "personal" + admin con `verify_password(...) is True`; (2) segunda llamada mismo email → `pytest.raises(SystemExit)`
- [ ] VERDE. CLI: `python -m scripts.create_admin --email admin@example.com`

### Task 14: Scaffolding frontend
- [ ] `npm create vite@latest admin-web -- --template react-ts` (los dos `--` son obligatorios en npm)
- [ ] `cd admin-web && npm install`
- [ ] `npm install tailwindcss @tailwindcss/vite @tanstack/react-query react-router-dom && npm install -D @types/node`
- [ ] `src/index.css` = `@import "tailwindcss";`; `vite.config.ts` con plugins react+tailwindcss, alias `@`→`src`, proxy `/api` (target `http://localhost:8000`, `changeOrigin: true`) y `/ws` (target `ws://localhost:8000`, `ws: true`)
- [ ] ANTES del init: añadir `"baseUrl": "."` y `"paths": {"@/*": ["./src/*"]}` en `tsconfig.json` Y `tsconfig.app.json` (prerrequisito oficial para Vite, no plan B)
- [ ] `npx shadcn@latest init` SIN `-d` (el `-d` actual fuerza plantilla Next.js y salta la detección de Vite)
- [ ] `npx shadcn@latest add button input card label -y`
- [ ] `npm run dev` → plantilla renderiza en http://localhost:5173

### Task 15: Login: api client + auth + pantalla
**Crea:** `src/types.ts`, `src/lib/{api,ws}.ts`, `src/auth/{AuthContext,ProtectedRoute}.tsx`, `src/hooks/useLogin.ts`, `src/pages/LoginPage.tsx`. **Modifica:** `src/main.tsx`, `src/App.tsx` (limpiar plantilla).
**Interfaces TS:**
```ts
export interface User { id: string; email: string; full_name: string | null; role: string; tenant_id: string; bot_name: string }
export interface LoginResponse { access_token: string; token_type: string; user: User }
export interface FeedEvent { id: string; type: string; tenant_id: string; created_at: string;
  data: { message_id?: string; conversation_id?: string; contact_id?: string;
          contact_wa_id?: string; push_name?: string | null; direction?: string; preview?: string | null } }
export type WsStatus = "connecting" | "open" | "closed"

export class ApiError extends Error { status: number }
export function authHeaders(): Record<string, string>          // Bearer desde localStorage "asistente_token"
export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T>
export async function loginRequest(email: string, password: string): Promise<LoginResponse>
export function buildWsUrl(token: string): string              // ws(s)://host/ws/events?token=...
export function useAuth(): { user: User | null; token: string | null; login(...): Promise<void>; logout(): void }
export function useLogin(): UseMutationResult<void, Error, { email: string; password: string }>
```
- [ ] `LoginPage.tsx` (español): Card centrada, "Correo electrónico", "Contraseña", "Iniciar sesión" (disabled → "Ingresando…"), error 401 → "Credenciales inválidas", éxito → `navigate("/")`
- [ ] Verificación manual: login ok navega al dashboard vacío; password mal → mensaje de error

### Task 16: Dashboard + feed en vivo (E2E)
**Crea:** `src/hooks/useEvents.ts`, `src/components/MessageFeed.tsx`, `src/pages/DashboardPage.tsx`.
**Interfaces:**
```ts
export function useEvents(token: string | null, onAuthError?: () => void): { events: FeedEvent[]; status: WsStatus }
// onopen → "open"; onmessage → JSON.parse, ignorar type==="connected", prepend (cap 50);
// onclose → "closed"; code===1008 → onAuthError() (logout); si no, reintentar en 2 s
```
- [ ] `DashboardPage`: header "Panel de {bot_name}", correo, "Cerrar sesión"; badge de conexión ("Conectado"/"Reconectando…"); `MessageFeed` con hora (`Intl.DateTimeFormat("es-CO")`), wa_id, push_name, preview y badge del tipo; vacío → "Sin eventos todavía. Envía un mensaje al webhook para verlo aquí."
- [ ] E2E: con el dashboard abierto, repetir el POST del webhook con OTRO `key.id` → aparece en < 1 s sin recargar

### Task 17: README + lint + verificación final + commit único
- [ ] `README.md`: descripción, requisitos, puesta en marcha, desarrollo, tests/lint, alcance F1
- [ ] `ruff check .` desde `backend/` → corregir
- [ ] Ejecutar la secuencia completa de la sección G y reportar comandos + resultados reales
- [ ] Commit único (lista explícita; verificar con `git status` que `.env` y `docs/MODULOS.md` NO quedan staged):
```powershell
git add .gitignore .env.example README.md docker-compose.yml backend admin-web docs/superpowers/plans/2026-10-10-fase-1-esqueleto.md
git commit -m "feat: fase 1 - esqueleto de punta a punta" -m "Backend FastAPI con 10 tablas (Alembic), JWT, webhook WhatsApp idempotente, canal Evolution stub, WebSocket de eventos, seed de admin, panel React (login + feed en vivo) y tests." -m "Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

## G. Secuencia de verificación final (PowerShell)

```powershell
# 1. Infra
docker compose up -d ; docker compose ps          # → ambos "running (healthy)"

# 2. Variables locales (una vez)
Copy-Item .env.example .env                        # editar JWT_SECRET con valor real

# 3. Venv (una vez)
python -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install -U pip
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt -r backend\requirements-dev.txt

# 4. Migración (desde backend/)
cd backend ; .\.venv\Scripts\Activate.ps1           # si lo bloquea: usar .\.venv\Scripts\alembic.exe
alembic upgrade head                                # → "Running upgrade -> <rev>, create base tables"
docker exec asistente_postgres psql -U asistente -d asistente -c "\dt"   # → 10 tablas + alembic_version

# 5. Seed
python -m scripts.create_admin --tenant-name "Personal" --email admin@example.com   # pide contraseña

# 6-7. Backend + health
uvicorn app.main:app --reload --port 8000 --reload-dir app    # → "Uvicorn running on http://127.0.0.1:8000"
curl http://localhost:8000/health                            # → {"status":"ok"}

# 8. Login
Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/v1/auth/login -ContentType "application/json; charset=utf-8" `
  -Body '{"email":"admin@example.com","password":"<la-del-seed>"}'    # → access_token + bot_name "Aura"

# 9. Webhook idempotente (¡dos veces, mismo key.id!)
$h = @{ "X-Tenant-Slug" = "personal" }
$p = '{"event":"messages.upsert","instance":"auratest","data":{"key":{"id":"3EB0F9B1B5D6C7D8","remoteJid":"573001234567@s.whatsapp.net","fromMe":false},"pushName":"Juan Pérez","messageType":"conversation","message":{"conversation":"Hola, necesito una cotización"},"status":"RECEIVED"}}'
Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/v1/webhooks/whatsapp -Headers $h -ContentType "application/json; charset=utf-8" -Body $p
# 1ª → duplicate: False ; 2ª → duplicate: True
docker exec asistente_postgres psql -U asistente -d asistente -c "SELECT count(*) FROM messages;"   # → 1

# 10. Frontend
cd ..\admin-web ; npm install ; npm run dev        # http://localhost:5173 → login → Dashboard "Conectado"
# repetir el paso 9 con OTRO key.id → el mensaje aparece en el feed en < 1 s

# 11. Tests (crea/recrea asistente_test sola)
cd ..\backend ; pytest -v                           # → todos en verde, 0 failed

# 12. Lint
ruff check .                                        # → "All checks passed!"

# 13. WebSocket directo (opcional)
npx wscat -c "ws://localhost:8000/ws/events?token=<JWT-del-paso-8>"
# → {"type":"connected",...,"bot_name":"Aura"} ; al repetir el paso 9 llega "message.received"
# con token inválido → cierre inmediato con código 1008
```

---

## H. Riesgos y gotchas de este entorno

1. **psycopg en Windows**: `psycopg[binary]` (wheels win_amd64/py3.12) + URL `postgresql+psycopg_async://`. Fallback documentado si la instalación falla: asyncpg con `postgresql+asyncpg://` (una línea en `.env` + `env.py`).
2. **Event loops (pytest)**: engine creado en un loop no se usa en otro → fixtures Y tests en el MISMO loop de sesión: `asyncio_default_fixture_loop_scope="session"` + `asyncio_default_test_loop_scope="session"` (pytest-asyncio ≥0.26) + engine `scope="session"`; cliente Redis por request/conexión, nunca global cruzado de loop.
3. **CREATE DATABASE en fixtures**: psycopg no puede en transacción → engine admin con `isolation_level="AUTOCOMMIT"` (T5).
4. **uvicorn --reload + OneDrive**: el watcher dispara recargas espurias → `--reload-dir app` y `uvicorn[standard]`.
5. **Proxy /ws en Vite**: requiere `ws: true`; `/api` requiere `changeOrigin: true`. El prefijo `/ws` no colisiona con el HMR de Vite.
6. **JWT por query param en WS**: los browsers no permiten headers en `new WebSocket`; el token queda en la URL y uvicorn lo registra en el access log — trade-off documentado de F1 (local-only); nunca loguear la URL nosotros; fases futuras: ticket de un solo uso.
7. **CRLF / OneDrive**: `core.autocrlf=true` global; OneDrive sincroniza `.venv` y `node_modules` (lentitud, locks) y también `.env` → no poner claves reales de servicios mientras la carpeta siga sincronizada; recomendar al usuario excluir `.venv`, `node_modules` y `.env` de la sincronización. Fallos de escritura por lock → reintentar el comando.
8. **PowerShell ExecutionPolicy**: `Activate.ps1` puede estar bloqueado → invocar `.exe` del venv directamente. `getpass` falla sin TTY → en automatizaciones pasar `--password` explícito.
9. **Alembic**: ejecutar SIEMPRE desde `backend/`; `env.py` debe importar `app.models` (si no, autogenerate no ve tablas); primero `docker compose up -d`, después autogenerar contra la BD vacía.
10. **Tests de WebSocket**: sin automatización (httpx no soporta WS; TestClient síncrono rompe psycopg async) → verificación manual G.13 + E2E T16. Los tests obligatorios de spec (health + idempotencia) quedan automatizados.
11. **Webhook sin firma + Redis caído**: sin firma en F1 (deuda para F3 con `EVOLUTION_WEBHOOK_TOKEN`); el publish en `try/except` con log → si Redis cae, el webhook responde 200 igual.
12. **`.env.example` ignorado**: corregido en T0 con `!.env.example`.
13. **Login multi-tenant (supuesto documentado)**: sin header de tenant en el login; si un email existe en 2+ tenants → 400. Hoy código muerto; correcto mañana.
