# Catálogo de módulos — Asistente Personal

Piensa cada módulo como una habilidad del mismo asistente. Los mejores son los que hacen que el usuario vuelva solo (porque el bot le escribe primero) o que le ahorran o le recuperan dinero de forma visible.

## Módulos base (los usan todos los demás)

- **Identidad del asistente**: el bot se llama «Aura» por defecto; en onboarding le pregunta al usuario cómo quiere llamarlo y firma sus mensajes con ese nombre.
- **Recordatorios y agenda**: "recuérdame llamar al cliente de Laureles el jueves". Es el módulo que más hace volver al usuario.
- **Contactos y clientes (mini CRM)**: historial de cada cliente, cotizaciones, trabajos y notas. El bot recuerda quién es quién.
- **Notas por voz y tareas**: el técnico dicta y el bot lo ordena en tareas con fecha.
- **Resumen diario proactivo**: cada mañana, qué hay agendado, qué cotizaciones esperan respuesta y qué pagos están pendientes.
- **Archivos y documentos**: guardar y buscar PDFs, fotos de obra y facturas ("mándame la cotización de los Restrepo").
- **Memoria**: que el asistente recuerde preferencias y datos recurrentes del usuario.

## Módulos para oficios (los que más fácil se venden)

- **Seguimiento de cotizaciones**: escribe al cliente a los 3 y 7 días. Es probablemente el que más dinero recupera.
- **Cobro de cartera**: recordatorios amables de pagos pendientes con enlace de pago.
- **Informe de visita técnica**: fotos y audio se convierten en un PDF con hallazgos y recomendaciones.
- **Mantenimiento preventivo recurrente**: avisa a los clientes cuándo toca limpiar el aire o revisar el tablero. Genera ingresos repetidos.
- **Seguimiento de obra**: bitácora diaria, avance con fotos y reporte al cliente.
- **Materiales e inventario**: lista de materiales de cada cotización, pedido al proveedor y control de lo que sobra.
- **Rentabilidad por obra**: costo real contra lo cotizado, para saber qué trabajos dejan plata.
- **Cuadrillas**: asignar trabajos y visitas al personal y recibir su reporte por WhatsApp.
- **Garantías**: registrar qué se instaló, cuándo y hasta cuándo cubre la garantía.
- **Checklist normativo**: recordatorios por tipo de trabajo (RETIE, NTC 2050). Funciona como recordatorio, no como certificación.

## Módulos de asistente personal general

- **Correo y calendario (Gmail y Google Calendar)**: resumir el correo, proponer horarios, crear eventos. Siempre con confirmación humana antes de enviar algo.
- **Finanzas personales**: ingresos y gastos por voz («cobré 500 mil a Juliana», «gasté 45 mil en cable»), cartera con balance en vivo («cuánto tengo») y resúmenes por día/semana/mes.
- **Búsqueda en internet (web_search)**: «busca en internet el precio del cobre» trae resultados de DuckDuckGo al chat; «navega a [URL]» o «abre 2» (resultado de la última búsqueda) leen la página y traen el contenido. Sin API keys.
- **Búsqueda y consultas**: precios, fichas técnicas, normativa.
- **Traducción y redacción**: mensajes a clientes con buen tono.

## Módulos para poder venderlo

- **Multi-tenant y roles**: cada negocio con sus datos, usuarios y permisos.
- **Planes y suscripciones**: límites de uso, cobros y pruebas gratis.
- **Onboarding por WhatsApp**: que un usuario nuevo se configure conversando con el bot; empieza preguntándole cómo quiere llamarlo (por defecto «Aura»).
- **Control de costos de IA por usuario.**
- **Auditoría y logs**: qué hizo el bot y por qué.
- **Política de datos y consentimiento (Habeas Data).**

## Prioridad sugerida

| Orden | Módulo | Por qué |
|-------|--------|---------|
| 1 | Cotizador | Es tu punto de partida y valida el producto |
| 2 | Seguimiento de cotizaciones | Recupera dinero y se nota rápido |
| 3 | Recordatorios y agenda | Hace que el usuario vuelva cada día |
| 4 | Informe de visita técnica | Resuelve una tarea molesta y se comparte con el cliente |
| 5 | Cobro de cartera | Segundo módulo que más dinero mueve |
| 6 | Mantenimiento recurrente | Ingresos repetidos para el técnico |
| 7 | Correo y calendario | Convierte el bot en un asistente completo |
| 8 | Obras, inventario y rentabilidad | Más valor, pero más complejo |

## Un consejo

No construyas todos. Lanza los módulos 1 a 3 con unos pocos técnicos y mira cuáles usan de verdad antes de seguir. Los módulos que más pesan en una suscripción suelen ser los que recuperan dinero (seguimiento y cobro) y los que generan hábito (recordatorios y resumen diario).
