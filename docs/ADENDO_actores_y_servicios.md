# ADENDO: actores, niveles de acceso, módulo «Clientes» y «Servicios»

**Este adendo tiene prioridad sobre `docs/ESPECIFICACION.md` cuando haya conflicto.**

---

## 1. Los tres niveles de personas (vocabulario obligatorio)

```
NIVEL 1  Superadmin (Óscar)          → administra la PLATAFORMA
   │
NIVEL 2  Cliente de la plataforma    → negocio, persona o empresa que contrata el asistente
   │       (en el código: TENANT)       su dueño habla con el asistente por WhatsApp y usa su panel
   │
NIVEL 3  Cliente final               → persona a la que el dueño le vende o le cotiza
           (en el código: CONTACT)      NO usa la plataforma; es un registro del CRM del dueño
```

| Término | Qué es | En el código | En la interfaz |
|---|---|---|---|
| **Superadmin** | Óscar, dueño de la plataforma | `users.is_platform_admin = true` | Panel de plataforma |
| **Cliente** (de la plataforma) | Negocio, persona o empresa que paga por el asistente | `tenant` | **«Clientes»** (solo en el panel del superadmin) |
| **Dueño** | La persona que usa el asistente de su negocio | `user` del tenant, rol `owner` | Su propio panel |
| **Cliente final** | Quien le compra al dueño | `contact` | **«Mis clientes»** (CRM dentro de «Servicios»), solo en el panel del dueño |

**Reglas de nombres (no negociables):**
1. En código, tablas, rutas de API y variables **nunca uses `client` ni `cliente` solos**. Usa `tenant` para el nivel 2 y `contact` para el nivel 3.
2. En la interfaz, **«Clientes» a secas solo existe en el panel del superadmin** y significa negocios. En el panel del dueño, a sus compradores se les llama **«Mis clientes»**.
3. Un dueño **nunca** ve la palabra ni la pantalla «Clientes» de la plataforma.
4. Hoy existe un conflicto: la ruta `/clientes` redirige a `/servicios/crm` (los contactos del dueño) y la lista de negocios vive escondida dentro de `AdminPage.tsx` con el título «Mis clientes». Hay que separarlo (sección 3).

---

## 2. Qué puede hacer cada nivel

| Capacidad | Superadmin | Dueño (su tenant) | Cliente final |
|---|---|---|---|
| Ver todos los clientes (tenants) | Sí | No | No |
| Ver datos de su propio negocio | Sí (de cualquiera, con auditoría) | Solo el suyo | No |
| Crear, suspender o reactivar un cliente | Sí | No | No |
| Cambiar el plan de un cliente | Sí | Solo solicitar o pagar | No |
| Definir precios de planes | **Sí** | No | No |
| Definir qué servicios son gratis o de pago por plan | **Sí** | No | No |
| Apagar un servicio para todos (interruptor global) | **Sí** | No | No |
| Dar o quitar un servicio a un cliente concreto (excepción) | **Sí** | No | No |
| Ver si un servicio funciona (estado) | **Sí**, de todos | Solo de los suyos | No |
| Ver suscripciones, pagos y reembolsos de todos | **Sí** | Solo los suyos | No |
| Encender o apagar servicios incluidos en su plan | Sí | **Sí** | No |
| Usar cotizador, notas, CRM, recordatorios | Sí (vía cliente) | **Sí**, según su plan | No |
| Gestionar la instancia de WhatsApp compartida y los proveedores de IA | **Sí** | No | No |
| Ver conversaciones de un cliente | Sí, **con motivo y auditoría** | Las suyas | No |
| Iniciar sesión | Sí | Sí | **No** (no tienen cuenta) |

**El cliente final no tiene panel ni cuenta.** Es un registro en el CRM del dueño. Si el dueño activa el «modo atención al cliente» (`tenants.customer_mode`, apagado por defecto), el bot puede contestarle por WhatsApp, pero eso sigue sin darle acceso a nada.

---

## 3. Estructura de la interfaz

### 3.1 Sidebar del superadmin
| Orden | Ítem | Ruta | Qué contiene |
|---|---|---|---|
| 1 | Panel | `/` | Métricas de la plataforma (sección 7) |
| 2 | **Clientes** | `/clientes` | Los negocios que Óscar gestiona (sección 3.3) |
| 3 | **Servicios** | `/servicios` | Todos los servicios de la plataforma y su administración (sección 3.4) |
| 4 | Pagos y planes | `/pagos` | Precios de planes, suscripciones, pagos, webhooks, conciliación |
| 5 | Plataforma | `/plataforma` | Número de WhatsApp compartido, proveedores de IA, auditoría |

El ítem actual «Admin» se divide entre «Clientes», «Pagos y planes» y «Plataforma». La matriz gratis/VIP pasa a «Servicios».

### 3.2 Sidebar del dueño
| Ítem | Ruta | Qué contiene |
|---|---|---|
| Panel | `/` | Su resumen |
| Servicios | `/servicios` | Los servicios de su plan (cotizador, **Mis clientes** en `/servicios/crm`, recordatorios, notas…) |
| Mi negocio | `/negocio` | Datos fiscales, logo, asistente, plan y facturas |

El dueño **no** ve «Clientes», «Pagos y planes» ni «Plataforma». La ruta `/clientes` para un dueño redirige a `/servicios/crm` (compatibilidad con enlaces antiguos); para el superadmin abre la lista de negocios.

### 3.3 «Clientes» (superadmin): los negocios
**Lista:** buscador, filtros por plan y estado de suscripción, y columnas: nombre o razón social, tipo de cuenta, plan, estado de la suscripción, próximo cobro, uso de los últimos 30 días, costo estimado de IA, último mensaje.

**Detalle de un cliente** (reutiliza y mueve lo que hoy está en `AdminPage.tsx`):
- Datos del negocio: tipo de cuenta, razón social, NIT, correo, teléfono, ciudad, logo.
- Plan y suscripción: plan actual, historial, fechas, estado.
- **Servicios de este cliente:** lista con interruptores que respetan su plan, y excepciones (sección 5).
- Pagos y métodos de pago (solo token y últimos 4 dígitos).
- Uso y costo por servicio.
- Conversaciones: acceso **con motivo y auditoría** (sección 4).
- Acciones: cambiar plan, regalar o extender días (con motivo), suspender, reactivar, reembolsar.

### 3.4 «Servicios»: una sola pantalla, dos vistas según el rol
- **Superadmin:** catálogo completo. Por cada servicio: estado (operativo, degradado, caído, en mantenimiento), **gratis o de pago por plan** (la matriz que hoy está en Admin), interruptor global, cuotas por plan, número de clientes que lo usan, uso y costo de los últimos 30 días, errores recientes.
- **Dueño:** solo los servicios de su plan, con su interruptor; los que su plan no incluye se muestran bloqueados con la etiqueta «VIP» y una invitación a mejorar el plan.
- Los servicios funcionales (cotizador, CRM, recordatorios, notas, etc.) viven bajo `/servicios/<clave>`. Es lo que ya existe; no lo muevas.

---

## 4. Reglas de autorización (backend primero, frontend después)

1. **Dos familias de rutas separadas:**
   - `/api/v1/platform/...` (hoy `/admin`): solo `require_platform_admin`. Puede recibir `tenant_id` en la ruta.
   - `/api/v1/...` del dueño: el tenant **siempre** sale del token del usuario. **Ninguna ruta acepta `tenant_id` de un usuario que no sea superadmin.**
2. El frontend oculta lo que el rol no puede usar, pero **la autorización real es del backend**. Cada ruta de plataforma lleva su prueba de «un dueño recibe 403».
3. **Auditoría del superadmin:** toda lectura de contenido de un tenant (conversaciones, notas, archivos, contactos) exige un **motivo** y queda en `audit_log` (quién, a qué tenant, qué, cuándo, por qué). El superadmin es encargado del tratamiento de datos personales bajo la Ley 1581: no debe leer contenido sin necesidad.
4. **«Ver como» un cliente** (suplantación): solo con motivo, con aviso visible en pantalla y registrada en `audit_log`. Solo lectura por defecto.
5. **Segundo factor** obligatorio para el superadmin (código por correo o aplicación autenticadora).
6. Todo cambio de plan, precio, matriz, excepción, interruptor global, reembolso o suspensión queda en `audit_log`.

---

## 5. Motor de servicios (extender, no reemplazar)

Ya existen: `core/modules_registry.py`, `TenantModule`, `PlanEntitlement` (matriz gratis/VIP editable), `plan_prices`, `services/entitlements.py` (`apply_plan`, `module_allowed`, `expire_subscriptions`), `ServiceUsage`. **Reutilízalos.**

**Orden para decidir si el cliente X puede usar el servicio S:**
1. **Interruptor global** de S: si está apagado o en mantenimiento, no.
2. **Excepción por cliente** (`tenant_service_overrides`): si existe y no venció, manda (puede dar o quitar el servicio).
3. **Plan** del cliente (matriz `PlanEntitlement`, con los valores por defecto del código como respaldo).
4. **Cuota y uso** del periodo.
5. **Estado de la suscripción**: activa o en gracia sí; vencida baja al plan gratuito.

**Tablas nuevas o ampliadas:**
| Tabla | Contenido |
|---|---|
| `service_catalog` | `key`, nombre, descripción, categoría, orden, `default_paid` (hoy esto vive en `modules_registry.py`; puede quedarse allí y reflejarse) |
| `service_status` | `service_key`, `status` (operational, degraded, down, maintenance), mensaje visible, `source` (auto o manual), actualizado por y cuándo |
| `tenant_service_overrides` | `tenant_id`, `service_key`, `allowed`, cuota propia, **motivo**, `expires_at`, quién lo puso |
| `audit_log` | quién, acción, tenant, objeto, motivo, fecha, IP |
| `plan_entitlements` | ya existe; añadir cuota por periodo |

**Estado automático:** a partir de fallos recientes en `ServiceUsage` y eventos (por ejemplo, tasa de error alta del LLM o Evolution desconectada), el estado pasa a «degradado» o «caído»; el superadmin también puede ponerlo en «mantenimiento» a mano.

**Cuando un servicio no está disponible:** el bot responde con un mensaje claro al dueño («Este servicio está en mantenimiento, te aviso cuando vuelva»), nunca un error técnico; el panel muestra una franja de aviso; ninguna petición se pierde en silencio.

**Gratis o de pago:** se define **solo** en la matriz por plan y en `plan_prices`, ambas editables desde el panel. Los precios **no** van escritos en el código. Un cambio de matriz o de precio se aplica de inmediato con la misma lógica de `apply_plan` para re-sincronizar `TenantModule`.

---

## 6. Qué corregir de `docs/ESPECIFICACION.md` (v0.4)

La implementación ya usa **un solo número de WhatsApp compartido** para toda la plataforma, y el tenant se identifica por el teléfono del remitente (`channel_identities`). La especificación v0.4 describía por error una instancia de WhatsApp por negocio. Actualizar:
- Sección 1 (D2, D3, D4): un solo número compartido; el negocio se identifica por teléfono; cada negocio se registra con **un solo número**; solo existe el modo asistente (el «modo atención al cliente» queda apagado por defecto).
- Secciones 3, 4 y 5: `whatsapp_instances` son números **de la plataforma** (empieza con uno; el diseño permite un grupo de números), gestionados solo por el superadmin.
- Sección 6, pasos 11 y 12: no hay conexión de un «número del negocio»; el número desde el que escribe el dueño queda guardado como su identidad.
- Sección 14: quitar `tenant_id` de `whatsapp_instances`.
- Sección 17 (Fase 1): sustituir por «base de número compartido».

---

## 7. Métricas del Panel del superadmin
Clientes activos, en prueba, en gracia y vencidos; ingresos mensuales recurrentes; pagos fallidos; uso por servicio; costo de IA por cliente y margen; estado de la instancia de WhatsApp; errores recientes; servicios con estado distinto de «operativo».

---

## 8. Pruebas obligatorias
- Un dueño recibe 403 en **todas** las rutas de plataforma (prueba parametrizada sobre el router).
- Un dueño no puede leer ni modificar datos de otro tenant pasando su identificador.
- `/clientes` abre la lista de negocios para el superadmin y redirige a `/servicios/crm` para un dueño.
- Cambiar la matriz gratis/VIP o el precio de un plan sincroniza los servicios de los clientes afectados.
- Interruptor global apagado: el bot rechaza el servicio con el mensaje de mantenimiento y se registra el evento.
- Excepción por cliente con vencimiento: deja de aplicar al vencer.
- Leer conversaciones de un cliente sin motivo falla; con motivo, queda en `audit_log`.
- Servicio con alta tasa de error pasa a «degradado» y vuelve a «operativo» al normalizarse.
