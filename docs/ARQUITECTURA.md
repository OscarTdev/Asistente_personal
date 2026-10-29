# Arquitectura de Aura

## 1. Límites del sistema

Aura es un monolito modular con tres superficies que comparten identidad,
persistencia y eventos, pero no permisos ni responsabilidades:

1. **Canal y conversación**: WhatsApp recibe eventos, resuelve el tenant y
   entrega mensajes al orquestador.
2. **Panel del tenant**: Mini CRM, cotizaciones y servicios operativos. Solo
   puede leer y mutar datos de su propio `tenant_id`.
3. **Plataforma**: el superadmin gestiona clientes registrados de Aura,
   planes, entitlements, bloqueo y métricas agregadas. No es el Mini CRM de
   ningún tenant.

La regla de aislamiento es estructural: cada consulta operativa debe contener
`tenant_id`; las consultas de plataforma deben excluir `Tenant.is_platform`.

## 2. Capas y patrones

### Adaptadores

- `app/api/v1/*`: HTTP, validación Pydantic y códigos de error.
- `app/channels/*`: Adapter para Evolution API y futuros canales.
- `admin-web/src/lib/api.ts`: Adapter HTTP del frontend.

Los adaptadores no deben contener reglas de negocio ni consultas agregadas
complejas.

### Casos de uso

- `app/services/*`: Application Service/Use Case.
- `app/services/platform_admin.py`: métricas y lifecycle de tenants de
  plataforma, reutilizable desde HTTP, chat o workers.
- `app/services/entitlements.py` y `service_engine.py`: políticas de plan y
  disponibilidad de servicios.

### Dominio y persistencia

- `app/models/*`: entidades SQLAlchemy.
- `app/services/*`: reglas que coordinan entidades y transacciones.
- Las consultas repetibles deben evolucionar a Query Objects o repositorios
  especializados, no copiarse entre routers.

### Presentación

- Las páginas React consumen hooks TanStack Query.
- El panel normal y el panel de plataforma tienen rutas y navegación
  distintas.
- Los DTOs de plataforma (`TenantAdminSummary`, `PlatformAdminStats`) no se
  reutilizan como DTOs del Mini CRM.

## 3. Flujo de una petición

1. El webhook valida secreto e idempotencia.
2. El adapter de canal normaliza el evento.
3. La resolución de identidad obtiene el `tenant_id`.
4. El caso de uso valida estado del tenant y entitlement.
5. Se ejecuta la transacción y se registra uso/auditoría.
6. El canal envía la respuesta; los trabajos lentos deben ir a ARQ/Redis.

El panel sigue el mismo principio: dependencia de autenticación, policy de
rol/tenant, caso de uso y respuesta DTO.

## 4. Complejidad actual y objetivo

| Operación | Antes | Ahora/objetivo |
|---|---:|---:|
| Lista de tenants | `O(T + C + Q + M + U + S)` en memoria | `O(P + C_P + Q_P + M_P + U_P + S_P)` por página |
| Estadísticas globales | `O(T + M + Q + U + S)` | Igual asintótico, agregación en PostgreSQL y `O(S)` memoria |
| Historial de conversación | `O(H)` por límite de mensajes | `O(H)` con índice por `(conversation_id, created_at)` |
| Contactos por tenant | `O(C)` | `O(C_t)` con índice y paginación |
| Dashboard tenant | varias agregaciones `O(C_t + Q_t + M_t + U_t)` | mantener SQL agregado; evitar materializar filas |
| Dispatcher conversacional | `O(I)` handlers revisados | objetivo `O(1)` para comandos exactos mediante registro |

Donde `T` es el total de tenants, `P` la página solicitada, `C/Q/M/U` filas de
contactos/cotizaciones/mensajes/uso y `S` servicios. En consultas SQL, estas
cotas representan cardinalidad procesada; el rendimiento real depende de
índices y del plan de PostgreSQL.

## 5. Decisiones de refactorización

- **Service Layer**: las métricas y el cambio de estado de tenants viven en
  `platform_admin.py`, no en el router.
- **Query Object incremental**: el listado limita primero los tenants visibles
  y luego agrega conteos solo para esos IDs.
- **Policy**: `require_platform_admin` protege la superficie de plataforma;
  las policies de tenant deben seguir siendo independientes.
- **Adapter**: WhatsApp y OAuth no deben filtrarse hacia servicios de dominio.
- **Outbox/worker**: el siguiente paso para Fase F es persistir eventos de
  salida en una tabla outbox y publicarlos con ARQ/Redis. `BackgroundTasks`
  no debe ser la garantía de entrega.

## 6. Invariantes de seguridad

- Un usuario normal nunca puede invocar endpoints técnicos de Evolution.
- Un tenant bloqueado no debe iniciar nuevas operaciones ni trabajos
  proactivos; sus datos permanecen para recuperación.
- El tenant de plataforma no puede bloquearse ni aparecer como cliente.
- Google OAuth entrega enlaces al panel; las credenciales nunca se procesan
  como instrucciones dentro de WhatsApp.
- Las acciones administrativas mutables registran auditoría.

## 7. Próximas fases recomendadas

1. Extraer un `TenantDirectoryQuery` para devolver `items`, `total` y
   `next_offset`, manteniendo compatibilidad temporal con el endpoint actual.
2. Añadir índices compuestos para filtros y orden de tenants, uso y mensajes.
3. Introducir un registro tipado de comandos para reducir el coste lineal del
   orquestador sin tocar los handlers existentes de una vez.
4. Migrar loops de `main.py` a workers ARQ idempotentes con locks por tenant.
5. Crear outbox transaccional para mensajes, recordatorios y eventos OAuth.
6. Separar dashboard operativo y dashboard analítico; materializar métricas
   globales solo cuando el volumen lo justifique.

