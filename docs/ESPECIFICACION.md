# Especificación para el agente de desarrollo: Asistente Personal (v0.4 + Enmienda A)

Documento único y autosuficiente. Reúne todas las decisiones tomadas, el estado real del repositorio `OscarTdev/Asistente_personal`, los fallos conocidos y las fases de trabajo con criterios de aceptación.

> **ENMIENDA A (2026-10-14) — NÚMERO ÚNICO COMPARTIDO.** La plataforma tendrá **un único número de WhatsApp compartido** por todas las personas, negocios y empresas registradas. **No se crea un número ni una instancia por cada tenant.** El número del remitente identifica al usuario y lo relaciona con su cuenta (tenant_id) a través de `channel_identities`. Esta enmienda **reemplaza** D2 y D3 de la tabla de decisiones y las secciones 4.1 y 5 en todo lo que suponga instancias por negocio. Todos usan el mismo número para registrarse e interactuar; el backend separa datos, conversaciones, permisos, módulos, cuotas y suscripciones de cada cuenta.

---

## 0. Cómo debe trabajar el agente

Estas reglas aplican a todo el documento.

1. **Trabaja por fases** (sección 17). Antes de escribir código en cada fase, muestra un plan corto y espera aprobación.
2. **Cambios pequeños y verificables.** Un commit por tarea lógica (Conventional Commits). No mezcles fases.
3. **Cada requisito lleva pruebas.** Ejecuta `ruff check`, `pytest` y, si tocas el frontend, el build, y reporta el resultado **real**. Nunca digas que algo funciona sin haberlo ejecutado.
4. **No inventes APIs, parámetros, campos de payload ni versiones.** Todo lo marcado **[VERIFICAR]** debe comprobarse en la documentación oficial o con una prueba real antes de implementarse. Si no puedes comprobarlo, deja un `TODO` explícito y pregunta.
5. **Compatibilidad con el entorno del propietario:** Windows con Docker Desktop, Postgres en el puerto host `5433`, `127.0.0.1` en lugar de `localhost`, y `--loop asyncio:SelectorEventLoop` para psycopg async (ver `start.ps1` y `README.md`). No lo rompas.
6. **Idiomas:** código, nombres y mensajes de commit en inglés; textos de interfaz, mensajes del bot, PDFs y documentación en español (Colombia).
7. **Seguridad por defecto:** sin secretos en el repositorio, sin datos personales en logs, entradas validadas, aislamiento por tenant en cada consulta.
8. **No amplíes el alcance.** Si ves una mejora fuera de la tarea, anótala en `docs/PENDIENTES.md` y sigue.
9. Al cerrar cada fase, actualiza `README.md`, `CLAUDE.md` y `AGENTS.md` para que reflejen el estado real.
10. No envíes `.env`, claves ni datos reales de clientes a ningún servicio externo. Usa datos de prueba.

---

## 1. Visión y decisiones cerradas

**Producto:** un asistente por WhatsApp para vender como servicio a **múltiples clientes** (negocios de oficios en Colombia: electricidad, HVAC, instalaciones). Con el número único compartido (Enmienda A), el mismo número atiende a todos: quien no está registrado entra a onboarding; quien está registrado habla con su asistente; los clientes conocidos de un negocio quedan asociados a su cuenta y el bot calla con ellos salvo que el dueño active su atención. Empieza con un cotizador, pero la visión es un **asistente completo** (notas, archivos, agenda, correo, encuestas, ubicaciones, enlaces, Google y Excel).

| # | Decisión | Detalle |
|---|---|---|
| D1 | Multi-tenant | Cada negocio es un tenant; todas las tablas llevan `tenant_id` |
| D2 | ~~Un número por negocio~~ → **ENMIENDA A** | **Un único número compartido**; el remitente se identifica por su número (`channel_identities`), no por la instancia |
| D3 | ~~Dos puertas de entrada~~ → **ENMIENDA A** | **Una sola puerta**: el mismo número sirve para onboarding y para la operación; el modo se decide por el estado del remitente (desconocido → onboarding; dueño/equipo → asistente; cliente conocido → atención o silencio según configuración del negocio) |
| D4 | Dos roles en el chat | Dueño o equipo → **modo asistente**; cliente conocido de un negocio → **modo atención al cliente** (solo si el negocio lo activa); desconocido → **onboarding** |
| D5 | Espera de 5 segundos | Varios mensajes seguidos de la misma conversación se procesan como uno solo (sección 7) |
| D6 | Registro por chat | Tipo de cuenta, nombre, asistente, NIT, correo, logo, número guardado en base de datos |
| D7 | **Sin contraseña por chat** | La contraseña NO se pide ni viaja por WhatsApp; se crea con un enlace de un solo uso en una página de la plataforma |
| D8 | Documentos | PDF de **cotización** y de **cuenta de cobro**, con logo, razón social, NIT y correo del negocio |
| D9 | Pagos | **MercadoPago** (ya integrado); planes `trial`, `freemium`, `premium` |
| D10 | Ubicaciones | El bot puede enviar la ubicación de **cualquier lugar** que se necesite, con confirmación y sin exponer datos de otros clientes |
| D11 | Herramientas | Encuestas, ubicaciones, enlaces, Google (Sheets, Docs, Forms), Excel; todas con reglas de uso serio |
| D12 | Audio | Entiende notas de voz y puede responder en audio |
| D13 | LLM | Interfaz compatible con OpenAI (OpenRouter o NVIDIA NIM). El proveedor y el modelo son configurables |
| D14 | Canal sin dependencia | El núcleo (notas, archivos, memoria, catálogo) vive en la base de datos, no en WhatsApp |

**Nota sobre D7:** el propietario pidió originalmente que el bot pidiera la contraseña. Se cambió a un enlace de un solo uso porque la contraseña quedaría guardada en el historial de WhatsApp, en la tabla de mensajes y en los logs, y no se puede borrar de todos esos sitios. Si el propietario insiste, debe decidirlo explícitamente.

---

## 2. Estado actual del repositorio

**Stack existente:** FastAPI, SQLAlchemy 2 async, Alembic, Pydantic v2, psycopg 3 (`postgresql+psycopg_async`), Redis, PostgreSQL 16 con pgvector, ReportLab para PDF, SDK de OpenAI contra OpenRouter o NVIDIA NIM, Evolution API v2 (Baileys) en Docker, React 18 + Vite + TypeScript + Tailwind 4 + TanStack Query v4.

**Estructura:** `backend/app/{api/v1,channels,core,models,schemas,services}`, `backend/alembic/versions`, `backend/tests`, `admin-web/src/{pages,components,hooks,lib,auth}`, `docker-compose.yml`, `start.ps1`, `verify.ps1`, `docs/`, `.claude/skills/`.

**Ya existe (estado real, actualizado a la Enmienda A):** login JWT con roles y `is_platform_admin`; webhook de WhatsApp **autenticado por secreto compartido** (`X-Webhook-Secret`) e idempotente (`UNIQUE(tenant_id, whatsapp_message_id)`); WebSocket de eventos por tenant; catálogo con carga CSV; cotizaciones e ítems; PDF de cotización (con escape XML, sin estado interno); seguimiento a 3 y 7 días; registro de módulos y planes (`modules_registry.py`, `entitlements.py`); checkout y webhook de MercadoPago **idempotentes con validación de monto y vencimiento de suscripciones**; panel con catálogo, clientes, cotizaciones, seguimiento, conexión de WhatsApp y módulos; **onboarding conversacional por chat** (nombre del asistente → nombre del dueño → tenant en trial con menú de servicios); **asistente del dueño** con router de intenciones (cotizar por encargo, enviar mensajes a contactos, conversar); **`channel_identities`** con resolución perezosa del legado de WhatsApp (el núcleo no depende del canal); edición de clientes desde el panel de plataforma (backend).

**No existe:** cola de trabajos (hay `BackgroundTasks` y un bucle dentro del proceso web), registro por chat completo (consentimiento, NIT, correo verificado, logo, enlace de un solo uso), espera de 5 segundos, transcripción de audio, respuestas en audio, logo y datos fiscales, cuenta de cobro, notas, archivos, memoria, tareas, cuotas aplicadas, límite de tasa, CI, pruebas con Alembic, página Admin del panel.

### 2.1 Fallos conocidos (Fase 0)

**Corregidos ya (con pruebas):** B1 (`contact.phone_number`), B2 (`BytesIO` en `b64encode`), B3 (cotizaciones a $0), B4 (comodines ILIKE — falta pg_trgm con umbral), B5 (webhook sin autenticación — falta quitar `X-Tenant-Slug`), B6 (Docker expuesto — hecho), B7 (cotizaciones del bot en `draft` y PDF con `DRAFT` — resuelto con `sent_at` y modo dueño), B8 (pagos no idempotentes — hecho con UNIQUE, validación de monto y vencimiento), B10 (instancia única global — las rutas ya exigen platform admin), B12 (escape XML), B15 (higiene del repo — LICENSE, README, CLAUDE.md).

**Pendientes:**

| ID | Dónde | Problema |
|---|---|---|
| B4+ | `ai_extraction.py` | Matching por ILIKE escapado funciona, pero falta similitud (`pg_trgm`) con umbral y preguntar cuando es ambigua |
| B5+ | `webhooks.py`, `deps.py` | `X-Tenant-Slug` sigue existiendo como fallback; la Enmienda A lo elimina a favor del tenant de plataforma |
| B9 | `followup.py`, `main.py` | Se envía antes de registrar; el bucle vive en el proceso web: con varios workers hay mensajes duplicados |
| B11 | `services/quotes.py`, `api/v1/quotes.py` | `contact_id`, `conversation_id` y `catalog_item_id` no se validan contra el tenant |
| B13 | `auth.py`, `config.py` | Sin límite de intentos; sin igualar tiempos si el correo no existe; tokens de 24 h; passlib |
| B14 | `evolution.py` | Teléfonos completos en logs `DEBUG` |
| B16 | `ws.ts` | `ws://localhost:8000` fijo; `react-router` con 2 vulnerabilidades moderadas |
| B17 | `tests/conftest.py` | Esquema creado con `create_all`, no con Alembic: las migraciones no se prueban |

---

## 3. Arquitectura objetivo

```
Clientes, dueños y prospectos (un único número de WhatsApp compartido)
        │
        ▼
Evolution API (UNA instancia de plataforma)
        │ webhook firmado (X-Webhook-Secret)
        ▼
FastAPI ── valida secreto ── guarda mensaje (idempotente) ── encola
        │                                   │
        │                              Redis (cola ARQ, buffers, candados, pub/sub)
        ▼                                   ▼
PostgreSQL + pgvector            Workers ARQ
        ▲                          ├─ debounce y agrupación de mensajes (5 s)
        │                          ├─ agente / orquestador (LLM + herramientas)
Panel React ◄── WebSocket          ├─ transcripción de audio y síntesis de voz
                                   ├─ generación de PDF y archivos
                                   ├─ seguimientos, recordatorios, vencimiento de planes
                                   └─ procesamiento de pagos y eventos
```

**Reglas de arquitectura**
- Monolito modular. Sin microservicios.
- Los webhooks responden 200 rápido y procesan en la cola.
- Idempotencia por ID de mensaje del canal y por ID de evento de pago.
- Orden estricto por conversación (candado por conversación).
- Capa de canal abstracta (`Channel`): `send_text`, `send_document`, `send_voice_note`, `send_poll`, `send_location`, `send_presence`, `parse_incoming`, `download_media`.
- Proveedor de LLM y de voz detrás de interfaces (`LLMProvider`, `STTProvider`, `TTSProvider`).
- Dinero siempre en `Decimal`; pesos colombianos se muestran sin decimales.
- Prompts versionados; cada acción del agente queda en auditoría.

---

## 4. Canal de WhatsApp: número único compartido (Enmienda A)

### 4.1 Instancia
- **UNA sola instancia de Evolution** para toda la plataforma (la existente, `aura`), configurada en variables de entorno. Sin tabla `whatsapp_instances` por tenant; los límites de envío son **por tenant** (sección 4.3), no por instancia.
- El número de WhatsApp del bot lo conecta el propietario de la plataforma desde el panel (QR en el panel, nunca por chat). Los negocios **no** conectan números.

### 4.2 Webhook
- Valida el secreto compartido por cabecera (`WEBHOOK_SECRET`, sin valor por defecto, `hmac.compare_digest`). Ya implementado; la instancia de Evolution se configura con la cabecera vía `/webhook/set/{instance}`.
- El tenant **se resuelve por el número del remitente** (`channel_identities` con creación perezosa del legado), no por `payload["instance"]` ni por `X-Tenant-Slug`. La cabecera `X-Tenant-Slug` se elimina.
- Un remitente desconocido cae en el **tenant de plataforma** (onboarding y soporte); un remitente registrado cae en SU tenant con el rol de su identidad.
- Mensajes propios (`fromMe`): solo el auto-chat ("mensaje a ti mismo") del dueño de plataforma se trata como comando; el resto se ignora. Ya implementado.

### 4.3 Protección del número (riesgo de bloqueo) — adaptado a número compartido
- Límite de mensajes por minuto, hora y día **por tenant** (todos comparten la reputación del número: los límites protegen el número de toda la plataforma).
- Nunca mensajes en frío: solo responder a quien escribió, o seguimientos de cotizaciones ya enviadas con horario permitido (8:00 a 19:00 hora de Colombia).
- Opción de "darse de baja" respetada.
- Aviso por escrito del riesgo de bloqueo (Evolution/Baileys no es oficial) y recomendación de un número dedicado a la plataforma.
- Capa de canal abstracta lista para migrar a la Cloud API oficial.

### 4.4 Política de Meta (contexto de producto)
Desde el 15 de enero de 2026 Meta prohíbe en la API oficial de WhatsApp Business a los "proveedores de IA" cuando el asistente es el servicio principal; la atención al cliente sí sigue permitida. Implicación: el producto se posiciona como **herramienta de gestión y atención para oficios**. Las funciones de asistente general se mantienen **acotadas al negocio**. No se promociona como "ChatGPT en WhatsApp". El texto oficial debe revisarse antes de migrar a la API oficial.

---

## 5. Enrutamiento y roles (número compartido)

```python
resolved = await resolve_identity(db, channel=channel.identity_channel,
                                  external_id=parsed.wa_id,
                                  fallback_tenant=platform_tenant)
tenant = resolved.tenant
mode = "assistant" if resolved.is_owner_or_team else ("customer" if business_allows else "silent")
```

| Quién escribe al número compartido | Modo | Comportamiento |
|---|---|---|
| Remitente desconocido | **onboarding** | Registro por chat (sección 6); al terminar, su tenant queda en trial y su número queda como identidad `owner` |
| Dueño o equipo de un negocio (identidad `owner`/`team`) | **assistant** | Cotiza, agenda, consulta, configura. Solo ve datos de su tenant |
| Cliente conocido de un negocio (identidad `contact`) | **customer** o **silencio** | Atención al cliente SOLO si el negocio la activa (sección 8.2); por defecto el bot calla (sus respuestas alimentan el seguimiento) |
| Auto-chat del dueño de plataforma | **assistant** (plataforma) | Operación del propietario |

- Cada conversación se identifica por `(tenant_id, teléfono)`; nunca se mezclan datos entre negocios ni entre clientes.
- Los números se normalizan a un solo formato antes de comparar o guardar.
- `tenant.wa_id` se mantiene solo como legado con creación perezosa en `channel_identities` (`tenant_id`, `contact_id`, `channel`, `external_id`, `kind/role`: `owner`, `team`, `contact`).
- Un dueño agrega teléfonos del equipo desde el panel o por chat (identidad `team`).

---

## 6. Registro (onboarding) por chat

Ocurre en el **número compartido** cuando escribe un desconocido. Máquina de estados persistida en `onboarding_sessions` (`step`, datos parciales, expiración, reanudable, comando "cancelar"). El estado mínimo actual (nombre del asistente → nombre del dueño → tenant trial) es el paso 0; los pasos siguientes enriquecen el perfil.

**Principios:** una pregunta por mensaje; botones cuando se pueda; se puede responder por audio **excepto NIT y documentos**, que se piden por texto; todo campo opcional puede omitirse ("después"); el bot nunca repite números de documento completos.

**Pasos para negocio o empresa**
1. Saludo, aviso de privacidad y términos, con botones **Acepto** y **Ver política**. Se guarda el consentimiento (fecha, versión, canal).
2. Tipo de cuenta: **persona natural** o **negocio o empresa**.
3. Razón social y nombre comercial.
4. **NIT con dígito de verificación** (validar el dígito).
5. **Correo**, verificado con un código enviado a ese correo.
6. Teléfono, ciudad y dirección.
7. Nombre del asistente (por defecto «Aura»).
8. **Logo:** pedir la imagen; recomendar enviarla como *documento* para mejor calidad. Procesarla (sección 10.2). Mostrar **vista previa** del encabezado en un PDF de ejemplo y pedir confirmación; aceptar otra imagen o "sin logo".
9. Preferencia de respuesta: texto, audio o automático.
10. **Acceso al panel:** enlace de un solo uso (caducidad corta) para crear la contraseña. **Nunca se pide la contraseña por chat.**
11. Crear el tenant en plan `trial`, guardar el número del dueño como identidad `owner` y ofrecer el menú de servicios.
12. Mensaje de prueba y tres ejemplos de uso desde el propio asistente.

**Persona natural:** igual, pero el documento es la cédula (o NIT si lo tiene); el logo es opcional; sin logo el encabezado usa solo el nombre.

**Datos por tipo de cuenta**

| Dato | Persona natural | Negocio o empresa | Se exige |
|---|---|---|---|
| Nombre | Nombre completo | Razón social y nombre comercial | Al registrarse |
| Documento | Tipo y número | NIT con dígito de verificación | Antes de pasar a plan pago |
| Responsable | La misma persona | Representante legal o encargado (nombre y documento) | Antes de pasar a plan pago |
| Ciudad | Sí | Sí | Al registrarse |
| Dirección | Opcional | Opcional; necesaria para facturar | Antes de pasar a plan pago |
| Correo | Sí | Sí | Al registrarse |
| Responsable de IVA o régimen | Pregunta simple, "no sé" permitido | Igual | Antes de pasar a plan pago |
| Logo | Opcional | Opcional (se pide siempre) | Opcional |
| Datos bancarios | Opcional | Opcional | Solo para cuenta de cobro |

**Reglas:** pedir lo mínimo; validar formatos; cambiar de tipo de cuenta crea una nueva versión del perfil fiscal (los documentos ya emitidos conservan sus datos); los datos de identificación se cifran a nivel de aplicación y se enmascaran en logs y pantallas; el NIT y el documento se declaran bajo responsabilidad del usuario (subir el RUT es opcional y sirve para precargar con OCR).

---

## 7. Espera de 5 segundos (agrupación de mensajes)

**Comportamiento obligatorio**
- Si una conversación recibe varios mensajes seguidos, el bot espera a que pasen **5 segundos sin mensajes nuevos** y procesa todo el lote como un solo mensaje.
- **Tope de espera:** si se cumplen 20 segundos desde el primer mensaje del lote, se procesa igual.
- Audios e imágenes se transcriben o describen antes de unirse al lote, conservando el orden.
- **Candado por conversación:** un solo lote en proceso a la vez.
- Si llega un mensaje mientras el modelo trabaja y **aún no se envió nada**, se descarta esa respuesta y se procesa el lote completo.
- Si ya se envió la respuesta, los mensajes nuevos forman el siguiente lote.
- Mostrar **"escribiendo…"** durante la espera y el procesamiento **[VERIFICAR]** soporte de presencia en Evolution.

**Implementación sugerida (Redis + ARQ)**
```python
DEBOUNCE, MAX_WAIT = 5, 20

async def on_incoming(msg):                       # webhook: guarda y sale rápido
    await save_message(msg)
    await redis.rpush(f"batch:{conv}", msg.id)
    await redis.set(f"last:{conv}", now())
    await redis.set(f"first:{conv}", now(), nx=True)
    await queue.enqueue("process_batch", conv, defer_by=DEBOUNCE)

async def process_batch(ctx, conv):
    quiet  = now() - await redis.get(f"last:{conv}")
    waited = now() - await redis.get(f"first:{conv}")
    if quiet < DEBOUNCE and waited < MAX_WAIT:
        return await queue.enqueue("process_batch", conv, defer_by=DEBOUNCE - quiet)
    async with lock(f"lock:{conv}"):
        ids = await take_all(f"batch:{conv}")
        if not ids:
            return
        text = await merge_batch(ids)             # audios transcritos + textos + pies de foto
        reply = await agent.run(conv, text)
        if await has_new_messages(conv) and not reply.already_sent:
            return await requeue(conv)
        await deliver(reply)
        await redis.delete(f"first:{conv}")
```
**[VERIFICAR]** la semántica de ARQ (`defer_by`, `job_id`, reprogramación). Es válida otra implementación mientras cumpla los comportamientos de arriba.

**Pruebas:** tres mensajes en 3 segundos → una sola respuesta; mensaje cada 4 segundos sin parar → procesa a los 20 segundos; mensaje durante el procesamiento antes de enviar → se reprocesa todo; dos conversaciones distintas no se bloquean entre sí.

---

## 7.1 Confirmación del modelo (2026-10-14): así funciona con el número único

- **Un solo número de WhatsApp, el mismo para todos.** No se crea instancia por cliente.
- **El backend identifica quién escribe** por su número (normalizado) y carga su cuenta: datos, conversaciones, límites y plan.
- **Tipos de cuenta:** personal, empresarial y de negocio; cada una con sus usuarios autorizados, módulos habilitados y consumo.
- **Separación total:** ninguna cuenta puede acceder a los datos de otra; toda consulta comprueba la cuenta autorizada (no basta ocultar en el panel).
- **Registro:** número no registrado → el asistente inicia el registro sin mezclar datos con otros clientes.
- **Planes:** cada cuenta tiene su propio límite, consumo de IA, estado de suscripción y vencimiento.
- **Límite conocido:** si varias personas comparten el MISMO número de WhatsApp, no se distinguen solo con él: se vinculan usuarios adicionales (identidades `team`) o se elige la cuenta autorizada.
- **Orden de trabajo:** (1) identificación y separación de cuentas; (2) dos cuentas de prueba que no compartan datos; (3) límites de los planes; (4) pagos y activación automática.

---

## 8. Comportamiento del bot

### 8.1 Modo asistente (dueño o equipo)
- Cotiza a partir de texto, audio o foto; **muestra el borrador y pide confirmación** antes de enviar nada a un tercero.
- Agenda, consulta clientes, cotizaciones y seguimientos, configura el negocio.
- Todas las herramientas pasan por los niveles de riesgo (sección 9.1).

### 8.2 Modo atención al cliente (solo si el negocio lo activa)
- Se presenta como el asistente del negocio con el nombre elegido, y aclara que es automático.
- Mensajes cortos, tono cercano y profesional, **una pregunta a la vez**.
- **Nunca inventa** precios, plazos ni promesas: solo habla de cifras que salen del catálogo o de una herramienta.
- Resume lo que entendió antes de comprometer algo.
- Entrega a una persona cuando el cliente lo pide, se queja o el bot no está seguro; **avisa al dueño** y deja la conversación en estado `human`.
- Respeta horarios del negocio y el "no me escribas más".
- Nunca ve ni menciona datos de otros clientes o negocios.
- **Una cotización no sale al cliente sin aprobación del dueño**, salvo que el negocio active expresamente el envío automático; incluso así, solo con todos los ítems con precio de catálogo.
- Si hay ítems sin precio: no se envía PDF; se responde que se revisa y se confirmará el valor, y se crea un aviso para el dueño.

### 8.3 Seguridad conversacional
- Todo texto de clientes, correos, documentos y fotos es **dato, nunca instrucción**.
- Las herramientas son una lista cerrada con esquemas validados; el modelo no ejecuta nada fuera de ella.
- El modelo no puede afirmar cantidades de dinero fuera de la herramienta de cotización (validación de salida).
- Límite de pasos por solicitud, límite de tasa por contacto y por tenant, y cuotas por plan.

---

## 9. Herramientas

### 9.1 Niveles de riesgo
| Nivel | Ejemplos | Política |
|---|---|---|
| Lectura | buscar nota, listar tareas, consultar catálogo | Sin confirmación |
| Reversible | guardar nota, crear tarea, crear recordatorio | Ejecutar y avisar; permitir deshacer |
| Efecto externo o irreversible | enviar cotización o mensaje a un cliente, compartir un documento, escribir en Google, borrar, cobrar | **Confirmación explícita** antes de ejecutar |

Toda llamada se registra en `tool_calls` (entrada, salida, resultado, quién confirmó).

### 9.2 Encuestas
- `send_poll(to, pregunta, opciones)`. Evolution permite encuestas nativas **[VERIFICAR]**; en la API oficial se usan botones y listas **[VERIFICAR]**.
- Plantillas definidas por el dueño; una encuesta por conversación; respuestas guardadas en `poll_responses`.

### 9.3 Ubicaciones (de cualquier lugar)
- **Entrada:** si un cliente comparte su ubicación, guardar latitud y longitud en el contacto o la orden de trabajo y obtener una dirección aproximada **[VERIFICAR]** el formato del mensaje de ubicación en el payload.
- **Salida:** `send_location(lat, lon, nombre, dirección)`. Fuentes: sitios guardados del negocio; **cualquier lugar buscado por nombre o dirección** mediante un servicio de geocodificación configurable (`GEOCODER_PROVIDER`: Google, Mapbox u OpenStreetMap; revisar condiciones, costos y que el servidor público de OpenStreetMap no admite uso intensivo); y enlace de Google Maps armado con coordenadas.
- **Reglas:** las direcciones colombianas se geocodifican con errores, así que se **confirma** con el pin y la pregunta "¿Es este lugar?", o se ofrecen hasta tres candidatos; solo lugares públicos o que la propia persona haya dado; **nunca la dirección o ubicación de otro cliente**; límite de consultas de geocodificación por tenant; cada ubicación enviada queda en auditoría.

### 9.4 Enlaces
- **Lista de dominios permitidos** por tenant y global.
- El modelo **nunca inventa URLs**: solo usa enlaces generados por el sistema (pago, cotización, formulario, Google) o de la lista permitida.

### 9.5 Google (Sheets, Docs, Forms) y Excel
- Conexión OAuth por negocio, con **alcances mínimos** y tokens cifrados (`google_connections`).
- Leer sin confirmación; **escribir o compartir con confirmación**; nunca hacer público un documento sin confirmación explícita.
- **Excel:** el backend genera el `.xlsx` y lo envía como documento; solo datos del tenant; sin fórmulas inyectadas desde texto del cliente.

---

## 10. Documentos PDF

### 10.1 Tipos
| | Cotización | Cuenta de cobro |
|---|---|---|
| Número consecutivo por negocio y tipo | COT-0001 | CC-0001 |
| Fecha y ciudad | Sí | Sí |
| Vigencia | Sí | No |
| Ítems con cantidad, unidad y valores | Sí | Sí, o concepto resumido |
| Subtotal, IVA o AIU y total | Sí | Total |
| **Total en letras** | Opcional | Sí |
| Condiciones y plazo de entrega | Sí | No |
| Datos bancarios para el pago | Opcional | Sí |
| Firma | Opcional | Sí |

La cuenta de cobro la usan sobre todo independientes no obligados a facturar y **no reemplaza la factura electrónica** si el negocio sí está obligado. El texto legal exacto lo valida el contador del propietario; dejarlo configurable.

### 10.2 Logo y datos del negocio en el PDF
- **Encabezado:** logo a la izquierda; a la derecha razón social o nombre comercial, **NIT con dígito de verificación**, **correo**, teléfono, dirección y ciudad.
- **Sin logo:** encabezado solo con texto.
- **Procesamiento del logo:** aceptar JPG, PNG y WebP; **rechazar SVG**; limitar tamaño y píxeles (configurar el límite de Pillow contra imágenes "bomba"); reabrir y guardar como PNG para **eliminar metadatos EXIF**; redimensionar a un ancho máximo (por ejemplo 600 px) conservando la proporción; guardar en almacenamiento privado por tenant; servir con enlaces firmados.
- **Vista previa** en el registro y comando para cambiarlo después ("cambiar logo").

### 10.3 Calidad del PDF
- Tabla que se parte bien entre páginas, con encabezado repetido y números de página.
- Pesos colombianos sin decimales (`$ 1.250.000`).
- Total en letras con `num2words` **[VERIFICAR]** soporte del idioma `es_CO`.
- Fuente con tildes y eñes correctas; **todo texto de usuario o de WhatsApp se escapa** (`xml.sax.saxutils.escape`).
- No imprimir el estado interno; usar etiquetas en español.
- **Documento inmutable:** guardar una copia de los datos con los que se generó (`documents.snapshot`). Si el negocio cambia el logo, los PDF antiguos no cambian; cualquier edición crea una versión nueva.
- **Consecutivo** desde `document_counters` con bloqueo de fila; nunca derivado del UUID.
- Pruebas: conversión a imagen y comparación con una de referencia; casos de lista larga, nombres largos, tildes, logo grande y sin logo, texto con `<` y `&`.
- Mantener ReportLab; separar en un módulo con una plantilla por tipo de documento.

---

## 11. Planes, suscripciones y pagos (MercadoPago)

- Planes: `trial`, `freemium`, `premium`; entitlements por plan ya existentes.
- **Idempotencia:** restricción única `(provider, provider_ref)`; tabla `payment_webhook_events` que **guarda primero el evento y procesa después**, con reintentos; si la referencia ya existe, no hacer nada.
- Al aplicar un pago aprobado: validar `transaction_amount`, `currency_id` y el plan de `metadata`; extender desde `max(ahora, current_period_end)`, no reiniciar.
- Rechazar firmas con `ts` fuera de una ventana (por ejemplo 5 minutos). **[VERIFICAR]** en la documentación de MercadoPago la normalización de `data.id` antes de firmar.
- **Vencimiento:** tarea periódica que pasa a `past_due` y luego a `freemium`, con avisos al dueño por WhatsApp. Periodo de gracia de unos 5 días. Los datos no se borran.
- **Cuotas por plan** aplicadas de verdad (mensajes con IA, cotizaciones, almacenamiento, minutos de audio). Aviso al 80% y al 100%.
- Evaluar suscripciones recurrentes de MercadoPago **[VERIFICAR]** disponibilidad en Colombia.
- Reembolsos solo desde el panel de plataforma, con registro de quién y por qué.
- Factura electrónica: dejar el modelo (`invoices`) preparado; la integración con un proveedor se decide con el contador.

---

## 12. Audio

- **Entrada:** transcribir notas de voz con `STTProvider`; conservar el audio original; el lote de la sección 7 une las transcripciones con los textos.
- **Salida:** modos por usuario (texto, audio o automático; en automático, si escribió por audio se responde con audio).
- Cifras, direcciones, enlaces, números de documento, PDFs y confirmaciones irreversibles **siempre también en texto**.
- Versión hablada separada de la escrita: frases cortas, sin formato, cantidades dichas como se hablan, 30 a 45 segundos como máximo, diccionario de pronunciación (RETIE, NTC, AIU, materiales).
- Enmascarar documentos, correos y números largos antes de sintetizar.
- Convertir al formato de nota de voz que exige el canal con ffmpeg (normalmente OGG con Opus) **[VERIFICAR]**. Enviar con `send_voice_note`.
- Si la síntesis falla o tarda, responder primero en texto.
- Cuotas de minutos de audio por plan; registrar en `voice_replies`.
- Voz sintética con pocas opciones; **sin clonar voces**; aclarar en el saludo que el asistente es automático.

---

## 13. Módulos del asistente (después de la base)

Cada módulo es una herramienta del agente detrás de una bandera de activación por tenant (`tenant_modules`).

- **Notas:** guardar, buscar, editar y borrar por chat (borrado lógico recuperable); notas de voz con transcripción y audio.
- **Archivos:** guardar PDFs, fotos y planos con validación de tipo y tamaño, antivirus, OCR y extracción de texto; cuotas por plan.
- **Memoria y búsqueda:** búsqueda híbrida (texto completo y pgvector) sobre notas, archivos, mensajes y clientes; hechos confirmados por el usuario en `memories`, visibles y borrables desde el panel.
- **Tareas y listas, recordatorios y agenda:** únicos y recurrentes; resumen diario y semanal.
- **Correo y calendario (Google):** resumir, proponer horarios, crear eventos; enviar siempre con confirmación.
- **Finanzas simples, informe de visita técnica, obras, inventario, rentabilidad, cartera, mantenimiento y garantías, checklist normativo (solo recordatorios, nunca certificación).**

Prioridad: seguimiento de cotizaciones, recordatorios y agenda, notas y archivos, informe de visita, cobro de cartera, el resto.

---

## 14. Modelo de datos (nuevo o modificado)

Todas las tablas nuevas llevan `tenant_id`, `created_at` y `updated_at`, salvo que se indique.

| Tabla | Contenido |
|---|---|
| `channel_identities` | `tenant_id`, `contact_id`, `channel`, `external_id` normalizado, `kind/role` (owner, team, contact) — **ya existe** |
| `onboarding_sessions` | `external_id`, `step`, `data` parcial, `expires_at` |
| `consents` | titular, tipo, versión de política, fecha, canal |
| `fiscal_profiles` | versionado: tipo de cuenta, nombre o razón social, tipo y número de documento (cifrado), dígito de verificación, representante, ciudad, dirección, correo de facturación, responsable de IVA, vigente desde |
| `tenant_branding` | `logo_file_id`, color, pie de página, datos bancarios cifrados |
| `documents` | tipo, número, estado, `snapshot` JSON, `file_id`, versión |
| `document_counters` | `(tenant_id, tipo)` → último número, con bloqueo de fila |
| `files` | nombre, tipo, tamaño, hash, ruta, estado de procesamiento, retención |
| `file_chunks` | texto y embedding |
| `notes`, `tags`, `taggings`, `folders` | notas y organización |
| `memories` | hechos confirmados con embedding |
| `tasks`, `reminders` | tareas y recordatorios |
| `conversations` | añadir: `mode` (assistant, customer), `state` (bot, human), `active_since` |
| `agent_runs`, `tool_calls` | auditoría del agente |
| `prompts`, `prompt_versions` | prompts versionados |
| `poll_responses`, `locations` | encuestas y ubicaciones |
| `google_connections` | OAuth cifrado, alcances, estado |
| `allowed_domains` | dominios permitidos de enlaces |
| `payment_webhook_events`, `payments` | eventos y pagos, con `UNIQUE(provider, provider_ref)` |
| `subscriptions` | `unique(provider, provider_ref)` ya existe; `sent_at` en `quotes` ya existe |
| `usage_counters` | contadores por periodo y tenant |
| `voice_replies` | duración, caracteres, costo, estado |
| `llm_usage` | ya existe; añadir voz y transcripción |

Reglas: claves foráneas compuestas `(tenant_id, id)` en tablas hijas para impedir referencias entre tenants; validar pertenencia en los servicios; pruebas automáticas que intenten leer datos de otro tenant y deban fallar.

---

## 15. Seguridad y cumplimiento

- Secretos solo en variables de entorno; `.env.example` sin valores reales; `JWT_SECRET` validado (mínimo 32 caracteres, distinto del texto de ejemplo); claves de Evolution y de webhooks sin valor por defecto.
- Docker: puertos solo en `127.0.0.1`; versión fija de las imágenes; contraseñas desde variables.
- Auth: límite de intentos y bloqueo temporal, igualar tiempos cuando el correo no existe, correo normalizado a minúsculas, tokens más cortos con renovación, cookie `HttpOnly` y `SameSite` o ticket de un solo uso para el WebSocket, `argon2` o `bcrypt` directo (no `passlib`).
- Webhooks (WhatsApp y MercadoPago): firma o secreto verificados, idempotencia, respuesta rápida.
- Cifrado de datos de identificación, datos bancarios y tokens OAuth a nivel de aplicación.
- Logs sin teléfonos completos ni contenido de mensajes.
- Archivos: validación de tipo real, tamaño, antivirus, rutas no predecibles, enlaces firmados con caducidad.
- Respaldos diarios de base de datos y archivos, con prueba de restauración.
- **Habeas Data (Ley 1581 de 2012):** política de tratamiento publicada, consentimiento registrado, derechos de conocer, actualizar, rectificar y suprimir (exportar y borrar desde el panel), retención configurable, y revisión legal de transferencias internacionales (proveedores de IA, voz y geocodificación).
- Auditoría de qué hizo el bot y por qué.

---

## 16. Calidad

- `ruff check` y `ruff format` aplicados; type hints; `pytest` con Postgres y Redis; las pruebas deben crear el esquema con **Alembic** (`alembic upgrade head`) y verificar que no hay diferencias con los modelos.
- **CI en GitHub Actions:** lint, tipos, pruebas con Postgres y Redis, `alembic upgrade head`, `pip-audit`, `npm audit`, build del frontend.
- Frontend: `tsc` en el build, lint y pruebas básicas; actualizar `react-router`; `wss://` derivado de `location`; fijar `engines`.
- Pruebas obligatorias por fase (sección 17). Cobertura mínima para orquestador, PDF, pagos, enrutador, agrupación de mensajes y registro.
- Backend con archivo de bloqueo de versiones.
- Documentación al día al cerrar cada fase.

---

## 17. Fases (adaptadas a la Enmienda A y al estado real del repo)

Cada fase termina con: `ruff check` limpio, `pytest` verde, migraciones aplicables desde cero, documentación actualizada y un resumen de comandos ejecutados con su resultado real.

### Fase 0: correcciones (B1–B17) — **grande parte hecha**
**Ya corregidas con pruebas:** B1, B2, B3, B4 (básico), B5 (secreto), B6, B7, B8, B10, B12, B15.
**Pendientes:** B4+ (`pg_trgm` con umbral y preguntar en ambigüedad), B5+ (eliminar `X-Tenant-Slug`: los desconocidos van al tenant de plataforma), B9 (reclamar-antes-de-enviar + horario), B11 (validación de referencias cross-tenant + FK compuestas), B13 (auth endurecida), B14 (logs sin teléfonos), B16 (`ws.ts`, react-router), B17 (Alembic en conftest).

### Fase 1: núcleo multi-canal — **base ya construida**
**Ya existe:** `channel_identities` con resolución perezosa, roles `owner`/`contact`, resolución por remitente, onboarding mínimo, API admin de identidades.
**Pendiente:** rol `team` (teléfonos del equipo), tenant de plataforma explícito para onboarding/soporte, modo `customer` configurable por negocio, límites de envío por tenant sobre el número compartido, sin `X-Tenant-Slug`.
**Aceptación:** dos tenants con cuentas distintas no se mezclan (prueba); un admin de un tenant no puede tocar datos de otro; el rol sale del remitente; desconocido → onboarding en el tenant de plataforma.

### Fase 2: cola y espera de 5 segundos
**Alcance:** ARQ + Redis, sección 7, seguimiento al worker con reclamar-antes-de-enviar y horario permitido.
**Aceptación:** las cuatro pruebas de la sección 7 pasan; el seguimiento no duplica con dos workers.

### Fase 3: registro por chat completo
**Alcance:** sección 6 (consentimiento, tipo de cuenta, NIT con dígito, correo verificado, logo, enlace de un solo uso, preferencia de respuesta).
**Aceptación:** un desconocido completa el registro y queda con tenant `trial`; ninguna contraseña viaja por chat; NIT inválido se rechaza.

### Fase 4: documentos y marca
**Alcance:** sección 10: `fiscal_profiles`, `tenant_branding`, `documents`, `document_counters`, logo seguro, cotización y cuenta de cobro, pruebas visuales.
**Aceptación:** PDF con logo, NIT, correo y razón social; consecutivos por negocio; documentos inmutables; total en letras; texto malicioso no rompe el PDF.

### Fase 5: agente y herramientas
**Alcance:** secciones 8 y 9: registro de herramientas con niveles de riesgo y auditoría, confirmación del dueño, encuestas, ubicaciones, enlaces con dominios permitidos, Google y Excel.
**Aceptación:** ninguna acción de efecto externo sin confirmación; el modelo no inventa URLs ni cifras; todo queda en `tool_calls`.

### Fase 6: pagos y cuotas — **parcialmente hecha**
**Ya existe:** UNIQUE, validación de monto/moneda/plan, vencimiento con degradación, ventana de firma.
**Pendiente:** `payment_webhook_events` (guardar-primero), cuotas por plan aplicadas con avisos al 80/100%, reembolsos desde panel.
**Aceptación:** reenvío no cambia nada; monto distinto se rechaza; suscripciones vencen solas; cuotas bloquean y avisan.

### Fase 7: audio
**Alcance:** sección 12 (STT/TTS providers, modo por usuario, enmascarado, conversión a nota de voz).
**Aceptación:** nota de voz entra al lote y se transcribe; respuesta en audio incluye texto con cifras; si falla la voz, responde en texto.

### Fase 8: módulos del asistente (por módulo)
Notas → Archivos → Memoria/búsqueda → Tareas/Recordatorios → Correo/Calendario. Cada uno detrás de su bandera, con cuotas y pruebas de aislamiento.

### Fase 9: paneles, endurecimiento y lanzamiento
Panel de plataforma (clientes, planes, identidades, chat), panel del negocio, CI completo, respaldos con prueba de restauración, políticas legales, pruebas de carga y seguridad.

---

## 18. Decisiones abiertas y cosas a verificar

**Decisiones del propietario pendientes**
1. Número compartido confirmado (Enmienda A): la reputación del número es de toda la plataforma — los límites por tenant protegen a todos.
2. Proveedores de geocodificación, voz (STT/TTS), OCR y almacenamiento.
3. Precios y cuotas exactos de cada plan (premium: COP $29.000/mes definido).
4. Modo de envío automático de cotizaciones (por defecto desactivado).
5. Retención de mensajes, audios y archivos.
6. Datos fiscales obligatorios (propuesta: antes del primer plan pago).
7. Texto legal de la cuenta de cobro, con el contador.
8. App propia o PWA como canal adicional.

**[VERIFICAR] antes de implementar**
- Mensajes de ubicación, encuestas, presencia ("escribiendo") y notas de voz en Evolution.
- Semántica de ARQ para reprogramar trabajos.
- Normalización de `data.id` en la firma de MercadoPago y disponibilidad de suscripciones recurrentes en Colombia.
- Idioma `es_CO` en `num2words`.
- Texto vigente de los términos de WhatsApp Business sobre asistentes de IA.

---

## 19. Variables de entorno

```
POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB
DATABASE_URL=postgresql+psycopg_async://...@127.0.0.1:5433/...
REDIS_URL=redis://127.0.0.1:6379/0
JWT_SECRET            # mínimo 32 caracteres, sin valor por defecto
WEBHOOK_SECRET        # sin valor por defecto (ya implementado)
ENCRYPTION_KEY        # para campos sensibles; sin valor por defecto
EVOLUTION_API_URL=http://127.0.0.1:8080
EVOLUTION_API_KEY     # sin valor por defecto
LLM_API_KEY, LLM_BASE_URL, LLM_MODEL
STT_PROVIDER, STT_API_KEY
TTS_PROVIDER, TTS_API_KEY
MERCADOPAGO_ACCESS_TOKEN, MERCADOPAGO_WEBHOOK_SECRET, MERCADOPAGO_NOTIFICATION_URL
GEOCODER_PROVIDER, GEOCODER_API_KEY
GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET
STORAGE_BACKEND, STORAGE_BUCKET, STORAGE_ENDPOINT
FOLLOWUP_DAYS=3,7
```
