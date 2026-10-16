# Asistente Personal (Aura) — Estado Real del Proyecto

## 15 servicios construidos y funcionando

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

## 15 intenciones del router

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
chat → Conversación general
```

## Modelo de negocio

- **Un número de WhatsApp compartido** para todos los clientes
- **Onboarding automático**: desconocido escribe → registro completo → tenant en trial
- **Planes**: trial (gratis) → freemium (método de pago) → premium ($29.000/mes)
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

## Pendiente (Google + infraestructura)

| Pendiente | Descripción |
|---|---|
| **Correo y calendario** | Gmail, Calendar, Sheets, Docs, Forms, Drive (OAuth) |
| **Resumen diario** | "Qué tengo hoy" al despertar (ya construido en backend por otra sesión) |
| **TTS** | Responder en voz (Edge TTS ya instalado, falta activar respuesta) |
| **Cola ARQ** | Migrar workers a ARQ para producción (el debounce ya funciona en asyncio) |
| **CI** | GitHub Actions con Postgres + Redis, lint, types, tests |
| **Logo en PDF** | Pillow + almacenamiento de archivos |

## Próxima gran fase: Google

El módulo de "correo y calendario" se expande a **todas las tecnologías Google**:
- **Gmail**: resumir correo, detectar clientes, responder
- **Calendar**: crear eventos, proponer horarios, sincronizar
- **Sheets**: leer/escribir datos de clientes, catálogo, cotizaciones
- **Docs**: generar informes y documentos
- **Forms**: encuestas a clientes
- **Drive**: guardar archivos de obras
- **Maps**: ubicaciones de trabajos

Requiere OAuth 2.0 con Google (alcances mínimos por servicio, tokens cifrados).
