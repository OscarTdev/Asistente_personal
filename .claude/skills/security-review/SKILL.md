---
name: security-review
description: Revisión de seguridad y calidad antes de un commit o PR. Úsala al terminar una funcionalidad o cuando se pida revisar código.
---

# Revisión antes de dar algo por terminado

Revisa los cambios (`git diff`) con esta lista y reporta los hallazgos por severidad:
- Secretos o tokens en el código, logs o commits.
- Aislamiento por `tenant_id` en cada consulta y endpoint.
- Webhooks: firma verificada, idempotencia, respuesta rápida.
- Entradas sin validar; consultas SQL armadas con texto.
- Contenido de mensajes o correos tratado como instrucciones para la IA (inyección de prompts).
- Datos personales en logs; cumplimiento de Habeas Data (Ley 1581).
- Manejo de errores, reintentos y timeouts.
- Pruebas que cubran el cambio; lint y tipos limpios.

Primero lista los hallazgos y espera mi aprobación antes de corregir.
