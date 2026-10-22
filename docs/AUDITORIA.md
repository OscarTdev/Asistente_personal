# Auditoría Integral del Proyecto — Asistente Personal (Aura)

**Fecha**: 22 de Octubre de 2026  
**Alcance**: Backend (FastAPI, SQLAlchemy, servicios), Frontend (React + Vite + TypeScript), Base de Datos (PostgreSQL, Alembic), Infraestructura (Docker, Redis, Evolution API), Pruebas y Seguridad.

---

## 1. Resumen Ejecutivo y Estado Real

El proyecto se encuentra en un estado de madurez y funcionalidad mucho más avanzado de lo que describe el archivo `AGENTS.md`:

| Métrica / Componente | Estado Auditado |
|---|---|
| **Servicios activos** | **16 servicios funcionales** (Cotizador con IA, CRM, notas, recordatorios, cuentas de cobro, cobro con MercadoPago, informe de visita, garantías, mantenimiento preventivo, gastos, inventario, bitácora de obra, rentabilidad, Google Workspace OAuth, STT Whisper, TTS). |
| **Modelos de BD** | **39 modelos** en `app/models/` con aislamiento estricto multi-tenant (`tenant_id`). |
| **Migraciones Alembic** | **29 migraciones lineales** consolidadas hasta `becf22f7a662` (Google OAuth). |
| **Backend Lint (`ruff`)** | **100% limpio** (0 errores, 0 warnings). |
| **Frontend Build & Types** | **100% exitoso** (`vite build` y `tsc --noEmit` sin errores de compilación o tipos). |
| **Intenciones del Router** | **19 intenciones identificadas** con soporte de chat conversacional y fallback. |

---

## 2. Hallazgos de Seguridad

### Puntos Fuertes Identificados
1. **Multi-tenant estricto por diseño**: Todas las tablas de datos de inquilinos incluyen `tenant_id` y claves/índices foráneos compuestos. No hay fugas directas entre organizaciones.
2. **Webhooks Fail-Closed**: El webhook de WhatsApp (`/api/v1/webhooks/whatsapp`) exige la cabecera `X-Webhook-Secret`. Si no está configurada o no coincide, responde `401 Unauthorized`.
3. **Firmas HMAC en Pagos**: El webhook de MercadoPago implementa verificación de firma HMAC-SHA256, rechazo de firmas expiradas (> 300 segundos para prevenir ataques de repetición) y comparación en tiempo constante con `hmac.compare_digest`.
4. **Protección Anti-Inyección**: 
   - Consultas con `_escape_like` para prevenir inyección de comodines en `ILIKE` sobre el catálogo.
   - Sanitización XML en la generación de PDFs para evitar vulnerabilidades de marcado.
   - Principio arquitectónico respetado: la IA nunca genera precios; sólo extrae entidades y los precios provienen estrictamente del catálogo de la base de datos.
5. **Autenticación Robusta**:
   - Validación de fortaleza de `JWT_SECRET` al arranque (mínimo 32 caracteres, rechaza valores de ejemplo).
   - Segundo factor de autenticación (TOTP / 2FA) implementado para acciones sensibles de superadmin.
   - Los enlaces de registro y acceso inicial del bot utilizan tokens de un solo uso con expiración.

### Vulnerabilidades y Riesgos a Subsanar
1. **Doble archivo de variables de entorno (`.env` vs `backend/.env`)**:
   - `backend/app/core/config.py` define explícitamente `_ENV_FILE = repo_root / ".env"`.
   - Existe un archivo adicional `backend/.env` en el subdirectorio del backend con credenciales repetidas. Modificar `backend/.env` puede causar confusión en desarrollo ya que Pydantic ignora cambios hechos en él si busca en la raíz.
2. **Credenciales en entornos locales**:
   - Se encuentran claves activas en los `.env` locales (Groq STT, NVIDIA NIM, tokens de prueba de MercadoPago). Si bien `.gitignore` los excluye adecuadamente del control de versiones (verificado en todo el árbol de commits), se recomienda contar con políticas de rotación de claves una vez se despliegue a producción.

---

## 3. Arquitectura y Deuda Técnica

### 1. El "God File": `app/services/orchestrator.py` (Alta Prioridad)
- **Problema**: El archivo cuenta con **2.667 líneas de código y 91 KB**. Agrupa la lógica de despacho de 19 intenciones, llamadas al LLM, armado de documentos, generación de PDFs, llamadas a servicios secundarios y formateo de respuestas de WhatsApp.
- **Riesgo**: Alto acoplamiento, dificultad para probar intenciones de manera aislada y alto riesgo de colisiones en cambios concurrentes.
- **Solución Recomendada**: Refactorizar hacia un patrón de despachador desacoplado (`handlers/`).

### 2. Cola de Tareas en Producción (`BackgroundTasks` vs `ARQ + Redis`)
- **Problema**: El procesamiento asíncrono se realiza actualmente mediante `BackgroundTasks` de FastAPI y un debounce local en `asyncio`.
- **Riesgo**: Si el proceso de FastAPI se reinicia o cae mientras hay un mensaje encolado o un PDF generándose, el trabajo se pierde definitivamente sin reintentos persistentes.
- **Solución**: Completar la migración a la cola `ARQ + Redis` (planificada en la especificación).

### 3. Ejecución de Tests y Configuración de Pytest
- **Problema**: `pyproject.toml` se encuentra dentro de `backend/`. Si se invoca `pytest` desde la raíz del repositorio, `pytest-asyncio` se ejecuta en modo estricto y no toma las opciones de sesión configuradas, disparando alertas de `RuntimeWarning: coroutine was never awaited`.
- **Solución**: Añadir un archivo `pytest.ini` o `pyproject.toml` en la raíz que redirija a `backend/`, o estandarizar el script de prueba para que siempre ejecute dentro de `backend/`.

### 4. Mapeo de Puertos de Base de Datos
- `docker-compose.yml` mapea PostgreSQL al puerto del host **5433** (`127.0.0.1:5433:5432`) para evitar conflictos con instancias nativas de Postgres en Windows.
- Sin embargo, `AGENTS.md` indica erróneamente el puerto `5432`. Se debe corregir la documentación para evitar confusión a desarrolladores y agentes de IA.

---

## 4. Auditoría del Frontend (`admin-web`)

### Resultados
- **Compilación**: `vite build` genera el bundle de producción en 7.55s sin fallos.
- **Tipado estricto**: `npx tsc --noEmit` reporta **0 errores**.
- **Cobertura de interfaz**: Dispone de 16 vistas completas que cubren Administración de Plataforma, CRM de Clientes, Catálogo de Precios, Cotizador, Seguimiento (Follow-ups), Negocio/Branding, Integración con Google Workspace, etc.

### Observación Menor
- En `src/hooks/useContacts.ts` (línea 50):
  ```typescript
  queryFn: () => import('../lib/api').then((m) => m.fetchContactTags()),
  ```
  Se realiza una importación dinámica cuando `api.ts` ya es importado estáticamente en múltiples hooks. Cambiar a importación estática elimina la advertencia de Vite durante el empaquetado.

---

## 5. Auditoría de Documentación vs Realidad

Se identificó una desactualización importante en `AGENTS.md`:
1. **Estado del proyecto**: Dice "Fase 1 construida; Fase 2 en desarrollo", cuando en realidad la Fase 2, Fases de Automatización, Módulos Adicionales y la Fase Google ya están implementadas (como lo refleja fielmente `docs/ESTADO.md`).
2. **Migraciones**: Dice que `backend/alembic/versions/` está vacío, cuando ya existen **29 migraciones**.
3. **Puerto de Postgres**: Dice `5432` en lugar de `5433`.

---

## 6. Plan de Acción Recomendado

### Acciones Inmediatas Sugeridas:
1. **Actualizar `AGENTS.md`**: Reflejar el puerto 5433, las 29 migraciones de Alembic y el estado de 16 servicios funcionales.
2. **Eliminar el archivo huérfano `null`** en la raíz (generado por redirección errónea de terminal en Windows).
3. **Unificar configuración `.env`**: Remover `backend/.env` redundante para que todo el proyecto se configure limpiamente desde el `.env` raíz.
4. **Optimizar `useContacts.ts`**: Reemplazar el `import()` dinámico por el estático para eliminar el warning de Vite.
