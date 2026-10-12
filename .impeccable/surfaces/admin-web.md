---
version: 1
slug: "admin-web"
primary_target: "admin-web"
related_targets: []
---

# Surface brief — admin-web (panel de Aura)

## Scope and visitor mode

Panel de administración interno de Aura (React). Modo: **Operate** — el dueño entra a hacer una tarea concreta entre trabajos y salir; móvil y escritorio primera clase.

## Audience, job, action, proof, constraints

Dueño de negocio de oficios (CO), admin del tenant. Tareas: revisar actividad del bot, gestionar catálogo de precios en COP, armar/enviar cotizaciones (PDF), activar módulos. Prueba: precios siempre del catálogo, cambios visibles y persistentes. Restricciones: es-CO, cifras tabulares, sin assets de marca previos.

## Direction contract

THESIS: El panel es la mesa del conserje de un hotel boutique — el asistente discreto que toma nota de cada mensaje, guarda el libro de precios impecable y tiene las cotizaciones listas para entregar. Se niega al dashboard SaaS azul-genérico y al traje de ferretería del usuario.

OWN-WORLD: Crema de papel como suelo; paneles de papel claro con costuras de 1px y elevación mínima. **Verde botella comprometido del shell**: la sidebar es el uniforme del conserje. **Latón solo como detalle funcional**: riel de la sección activa, anillo de foco, sello de cambio. **Lacre** para erratas y acciones destructivas. Rótulos de papelería en versalitas espaciadas; cifras tabulares en todo COP.

STORY: el dueño llega al mostrador y el conserje ya tomó nota: fichas de mensaje recientes, el catálogo como libro limpio de precios, cotizaciones listas para entregar en PDF. Todo cambio queda anotado — retención en tinte pino con filo de latón hasta que el dueño lo ve — y los errores son notas de lacre persistentes, no toasts.

FIRST VIEWPORT: Panel — sidebar-mostrador en verde botella con riel de latón deslizándose a la sección activa; memberete con el nombre del bot (renombrable) como papelería del hotel; estado del asistente como "En servicio / Fuera de servicio"; fichas de mensaje apiladas sobre el despacho. En móvil el mostrador pasa a barra superior con pestañas subrayadas en latón.

FORM: "El conserje de boutique", candidato 1 del registro asistente (steer del usuario), elegido sobre ferretería en re-roll guiado. SEED: e130aaf4 → 38851810.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance.

## Signature moment

La ficha de mensaje (events/quotes como fichas de conserjería) + el riel de latón que se desliza al navegar + retención de cambio hasta ser vista.

## Inherited product disciplines (raised by earlier donors)

Acciones destructivas aisladas con espacio deliberado · costuras hairline sin sombras pesadas · retención de cambio hasta visto · errata persistente · cifras tabulares.

## Unresolved decisions

Modo oscuro (uso nocturno declarado) queda como fase futura; el crema actual debe servir de noche con contraste alto.
