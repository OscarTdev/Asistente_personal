---
name: google-setup
description: Guía de configuración de Google Workspace (OAuth 2.0) para el asistente. Úsala cuando necesites conectar Gmail, Calendar, Sheets o Docs.
---

# Configuración Google Workspace — Asistente Personal

## Requisitos previos
- Google Cloud Console project
- OAuth 2.0 Client ID (tipo "Aplicación web")
- Credenciales: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`
- Redirect URI registrada: `{PANEL_BASE_URL}/google/callback`

## Scopes necesarios
```
https://www.googleapis.com/auth/gmail.readonly
https://www.googleapis.com/auth/calendar
https://www.googleapis.com/auth/spreadsheets
https://www.googleapis.com/auth/documents
https://www.googleapis.com/auth/drive.file
```

## Flujo de conexión (desde el panel)
1. Dueño va a **Servicios → Google** y clica "Conectar"
2. Redirige a Google OAuth → dueño autoriza scopes
3. Callback guarda `refresh_token` en `google_connections` (cifrado)
4. Panel muestra "Conectado" + botón "Desconectar"

## Uso en el bot
- Módulo `email_calendar` debe estar activo en el plan del tenant
- Dueño pide: "resume mi correo", "agenda visita el jueves", "pasa gastos a Sheets"
- Bot usa `google_actions.py` + `google_api.py` → llama a APIs de Google
- **Confirmación obligatoria** antes de enviar correos o crear eventos

Ver `docs/GOOGLE.md` para pasos detallados.
