# Integración con Google Workspace

El dueño del negocio conecta **su propia cuenta de Google** desde el panel
(Mi negocio → Conectar Google) y el asistente puede entonces, **por chat de
WhatsApp**:

| Comando de chat | Qué hace |
|---|---|
| «resumime el correo» | Lista los últimos correos de su bandeja (solo lectura) |
| «escríbele un correo a Juliana diciendo que llego a las 3» | Prepara el borrador y pide **confirmación** antes de enviar |
| «qué tengo hoy / mañana / esta semana» | Su agenda de Google Calendar |
| «agenda visita de Juliana el jueves a las 3» | Crea el evento en su calendario |
| «pasa mis gastos a una hoja» | Exporta los gastos del mes a una hoja de cálculo nueva |
| «genera un informe del mes» | Documento en Google Docs con gastos y cotizaciones del mes |

Y desde el panel (API): encuesta de satisfacción en Google Forms
(`POST /api/v1/google/forms/satisfaction-survey`) y archivos recientes de
Drive (`GET /api/v1/google/drive/files`).

El módulo se llama **«Correo y calendario (Google)»** en Servicios y solo
está disponible en el **plan premium** (matriz de entitlements).

---

## 1. Configurar la plataforma (una sola vez, el superadmin)

La plataforma tiene UN client OAuth de Google; cada negocio conecta su
cuenta con ese client y sus tokens quedan en **su** fila
(`google_connections`, una por tenant).

### Paso a paso en Google Cloud Console

1. **Crear el proyecto**: <https://console.cloud.google.com> →
   «New project» → nombre sugerido: `asistente-aura`.
2. **Pantalla de consentimiento** (APIs & Services → OAuth consent screen):
   - User type: **External**
   - App name: `Aura`, correo de soporte y de contacto del desarrollador.
   - **Scopes**: agrega exactamente estos (botón «Add or remove scopes»):

     | Servicio | Scope |
     |---|---|
     | Correo del dueño | `https://www.googleapis.com/auth/userinfo.email` |
     | Gmail (leer) | `https://www.googleapis.com/auth/gmail.readonly` |
     | Gmail (enviar) | `https://www.googleapis.com/auth/gmail.send` |
     | Calendar (eventos) | `https://www.googleapis.com/auth/calendar.events` |
     | Sheets | `https://www.googleapis.com/auth/spreadsheets` |
     | Drive (solo archivos de la app) | `https://www.googleapis.com/auth/drive.file` |
     | Docs | `https://www.googleapis.com/auth/documents` |
     | Forms | `https://www.googleapis.com/auth/forms.body` |

   - **Test users**: mientras la app esté en modo «Testing», agrega el
     correo Google de cada dueño que vaya a conectar (o publica la app
     para producción cuando esté lista).
3. **Habilitar las APIs** (APIs & Services → Library, una por una):
   Gmail API, Google Calendar API, Google Sheets API, Google Docs API,
   Google Drive API, Google Forms API.
4. **Credenciales** (APIs & Services → Credentials → Create credentials →
   OAuth client ID):
   - Type: **Web application**
   - **Authorized redirect URIs**: la URL del panel terminada en
     `/google/callback`. En desarrollo:
     `http://localhost:5173/google/callback`. En producción, la del
     dominio real (puedes registrar las dos).
   - Copia el **Client ID** y el **Client Secret**.
5. **Variables en `.env`** (raíz del repo):

   ```env
   GOOGLE_CLIENT_ID=xxxx.apps.googleusercontent.com
   GOOGLE_CLIENT_SECRET=GOCSPX-xxxx
   # Opcional — vacío → {PANEL_BASE_URL}/google/callback
   GOOGLE_REDIRECT_URI=
   ```

   Reinicia el backend. Sin estas variables el endpoint
   `POST /api/v1/google/authorize` responde **422 con un mensaje claro**
   (nunca falla en silencio).

---

## 2. Cómo conecta el dueño su cuenta

1. Panel → **Mi negocio** → tarjeta **Cuenta de Google** → «Conectar Google».
2. El panel pide la URL de consentimiento al backend
   (`POST /api/v1/google/authorize`) y redirige el navegador a Google.
3. El dueño acepta los permisos en Google.
4. Google regresa al panel (`/google/callback?code=…&state=…`), el panel
   canjea el código (`POST /api/v1/google/callback`) y listo: la tarjeta
   muestra su correo conectado.
5. «Desconectar» revoca el token en Google y borra la fila del tenant.

El token de acceso dura ~1 hora; el backend lo **refresca solo**. Si el
refresh falla (contraseña cambiada, permisos revocados), la conexión pasa
a `is_active=false` y el bot le dice al dueño que reconecte en el panel.

---

## 3. Endpoints de la API

Todos bajo `/api/v1/google`, autenticados con Bearer token del panel. El
`status` acepta cualquier usuario autenticado del tenant; **el resto exige
rol `admin`** (el dueño). Errores: `409` = no conectado o
sesión expirada (reconectar), `422` = plataforma sin credenciales,
`502` = Google respondió con error.

| Método | Ruta | Qué hace |
|---|---|---|
| GET | `/status` | ¿Conectado? ¿configurado? correo y scopes |
| POST | `/authorize` | URL de consentimiento (state JWT de 10 min) |
| POST | `/callback` | Canjea el `code` y guarda los tokens del tenant |
| DELETE | `/disconnect` | Revoca en Google y borra la conexión |
| GET | `/gmail/summary?max_results=5` | Correos recientes (solo lectura) |
| GET | `/calendar/upcoming?days=7` | Agenda de los próximos N días |
| POST | `/calendar/events` | Crea un evento (ISO 8601, naive = hora Colombia) |
| POST | `/sheets/export-expenses` | Gastos del mes → hoja nueva con total |
| POST | `/docs/month-report` | Informe del mes → documento nuevo |
| GET | `/drive/files?max_results=10` | Archivos recientes (solo los creados por la app) |
| POST | `/forms/satisfaction-survey` | Encuesta de satisfacción lista para compartir |

---

## 4. Seguridad

- **Un tenant, una conexión**: `google_connections.tenant_id` es UNIQUE;
  toda consulta filtra por tenant. Los tokens de un negocio jamás cruzan
  a otro.
- **`state` firmado**: es un JWT (HS256, 10 min) que ata el flujo al
  tenant que lo inició. Un state de otro tenant → 403; un state vencido
  o falso → 401. Bloquea CSRF y conexiones cruzadas.
- **Confirmación humana**: el correo a un tercero pasa por
  `PendingAction` — el bot muestra el borrador y pregunta «¿Te lo envío?»;
  solo con «sí» llama a Gmail (regla §8.1: efectos externos requieren
  confirmación).
- **Nunca inventa**: el resumen de correo muestra lo que hay en la bandeja;
  el informe de Docs usa los datos reales de gastos y cotizaciones.
- **Revocación real**: «Desconectar» llama a `oauth2.googleapis.com/revoke`
  y además borra la fila.
- **Menor privilegio**: `drive.file` (solo lo creado por la app),
  `gmail.readonly` + `gmail.send` (ni borrar ni etiquetas), Forms solo
  para crear el cuerpo de la encuesta.

## 5. Detalles técnicos

- Sin SDK de Google: cliente REST con `httpx`
  (`backend/app/services/google_api.py`), fácil de mockear en tests
  (`backend/tests/test_google.py`, 24 pruebas).
- Capas: `google_oauth.py` (conexión/tokens) → `google_api.py` (REST
  puro) → `google_actions.py` (lógica de negocio, la usan el router y
  el orquestador).
- Zona horaria: Colombia es UTC-5 fijo (sin DST). Fechas «naive» se
  interpretan como hora Colombia y se convierten a UTC antes de llamar
  a Google; las respuestas se formatean de vuelta a hora local.
- Google Maps requiere su propia API key (no OAuth): queda pendiente.
