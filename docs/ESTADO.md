# Asistente Personal (Aura) — Estado Real del Proyecto

## 16 capacidades construidas y funcionando (14 módulos en el registro)

| # | Servicio | Comando por chat | Estado |
|---|---|---|---|
| 1 | **Cotizador con IA** | "Cotizale a Juliana 3 tomacorrientes" → PDF COT-0001 | ✅ |
| 2 | **Seguimiento de cotizaciones** | Automático a los 3 y 7 días, detección de respuesta | ✅ |
| 3 | **CRM (contactos)** | "Busca el contacto de Juliana" | ✅ |
| 4 | **Recordatorios y agenda** | "Recuérdame llamar a Juliana el jueves" | ✅ |
| 5 | **Notas** | "Guarda una nota: comprar 20m de cable" | ✅ |
| 6 | **Transcripción de voz (STT)** | Envías un audio → lo transcribe y procesa | ✅ |
| 7 | **Cuenta de cobro** | "Cuenta de cobro para Juliana por 500 mil" → CC-0001 | ✅ |
| 8 | **Cobro de cartera** | "Cobrale a Juliana 450 mil" → link de MercadoPago | ✅ |
| 9 | **Informe de visita** | "Informe de visita para Juliana: revisé el tablero" → IV-0001 | ✅ |
| 10 | **Mantenimiento preventivo** | "Programa mantenimiento de aire cada 6 meses" → aviso automático | ✅ |
| 11 | **Garantías** | "Registra garantía para Juliana: breaker 30A, 1 año" | ✅ |
| 12 | **Finanzas personales** | "Gasté 45 mil en cable" / "Cuánto he gastado este mes" | ✅ |
| 13 | **Inventario** | "Tengo 20 metros de cable" / "Qué inventario tengo" | ✅ |
| 14 | **Seguimiento de obra** | "Abre obra para Juliana" / "Registro: se instaló..." | ✅ |
| 15 | **Rentabilidad** | "Rentabilidad del trabajo de Juliana" | ✅ |
| 16 | **Correo y calendario (Google)** | "Resumime el correo" / "Qué tengo hoy" / "Pasa mis gastos a una hoja" | ✅ |

## Infraestructura

| Pieza | Detalle |
|---|---|
| **PostgreSQL 16** | 36 tablas, pgvector + pg_trgm, 15 migraciones |
| **Redis** | Debounce 5s, pub/sub de eventos, sesiones |
| **Evolution API v2** | WhatsApp (instancia única compartido) |
| **MercadoPago** | Checkout Pro + webhooks con firma HMAC, idempotencia |
| **Groq** | Whisper large-v3 (STT, gratis) |
| **Edge TTS** | Voz es-CO-SalomeNeural (gratis) |
| **NVIDIA NIM** | LLM compatible OpenAI (extracción, router de intenciones) |
| **Panel React** | Dashboard, catálogo, cotizaciones, CRM, admin |

## 19 intenciones del router

```
send_message → Enviar mensaje a un contacto
quote → Cotizar materiales
invoice → Cuenta de cobro
confirm → Confirmar/rechazar acción pendiente
note → Notas (guardar, buscar, listar, borrar)
reminder → Recordatorios con fecha
collection → Cobrar a un cliente
visit_report → Informe de visita técnica
maintenance → Mantenimiento preventivo
warranty → Garantías de lo instalado
expense → Registrar gastos
inventory → Inventario de materiales
site_log → Bitácora de obra
profitability → Rentabilidad de un trabajo
google_email → Resumir el correo / escribir a un contacto (con confirmación)
google_calendar → Consultar la agenda / agendar un evento
google_sheets → Exportar los gastos a una hoja de cálculo
google_docs → Generar el informe del mes en un documento
chat → Conversación general
```

## Modelo de negocio

- **Un número de WhatsApp compartido** para todos los clientes
- **Onboarding automático**: desconocido escribe → registro completo → tenant en trial
- **Planes**: trial (gratis) → freemium (método de pago) → premium ($19.900/mes)
- **Entitlements**: nadie enciende un servicio fuera de su plan
- **Confirmación del dueño**: nada se envía a un tercero sin "sí"
- **MercadoPago**: link de pago, webhook idempotente, vencimiento automático

## Seguridad

- Webhook fail-closed (X-Webhook-Secret)
- Contraseña JAMÁS por chat (enlace de un solo uso)
- Consentimiento Ley 1581 antes de pedir datos
- Aislamiento por tenant_id en cada consulta
- Docker solo en 127.0.0.1, sin claves por defecto
- PDFs con escape XML (anti inyección de marcado)

## Pendiente (infraestructura)

| Pendiente | Descripción |
|---|---|
| **Credenciales Google** | Crear el OAuth client en Google Cloud Console y poner GOOGLE_CLIENT_ID/SECRET en .env (guía: docs/GOOGLE.md) |
| **Google Maps** | Requiere API key propia (no OAuth) — pendiente |
| **Resumen diario** | "Qué tengo hoy" al despertar (ya construido en backend por otra sesión) |
| **TTS** | Responder en voz (Edge TTS ya instalado, falta activar respuesta) |
| **Cola ARQ** | Migrar workers a ARQ para producción (el debounce ya funciona en asyncio) |
| **CI** | GitHub Actions con Postgres + Redis, lint, types, tests |

## Fase Google: construida ✅ (commits 392182a y siguientes)

El módulo «Correo y calendario (Google)» ya está activo con las tecnologías:
- **Gmail**: resumir la bandeja + escribir correos con confirmación del dueño
- **Calendar**: consultar la agenda y agendar eventos (hora Colombia)
- **Sheets**: exportar los gastos del mes a una hoja nueva con total
- **Docs**: informe del mes (gastos por categoría + cotizaciones)
- **Forms**: encuesta de satisfacción lista para compartir
- **Drive**: archivos recientes de la cuenta conectada

Cada dueño conecta SU cuenta desde el panel (Mi negocio → Conectar Google),
con state JWT anti-CSRF y aislamiento total por tenant (24 pruebas en
tests/test_google.py). Falta solo crear las credenciales en Google Cloud
Console (docs/GOOGLE.md §1) y publicar la app cuando haya usuarios reales.
