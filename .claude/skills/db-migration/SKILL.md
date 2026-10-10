---
name: db-migration
description: Crear o modificar tablas y columnas con SQLAlchemy y Alembic. Úsala cuando cambie el esquema de la base de datos.
---

# Migraciones de base de datos

1. Modifica o crea el modelo en `backend/app/models/` (siempre con `tenant_id`, salvo la tabla `tenants`).
2. Genera la migración: `cd backend && alembic revision --autogenerate -m "<descripcion>"`.
3. Revisa a mano el archivo generado: índices, claves foráneas, valores por defecto y el `downgrade`.
4. Aplica con `alembic upgrade head` y comprueba que `alembic downgrade -1` y volver a subir funcionan.
5. Actualiza los esquemas Pydantic y las pruebas afectadas.
6. Nunca edites una migración ya aplicada en otro entorno; crea una nueva.
7. Reporta qué tablas o columnas cambiaron y el resultado real de los comandos.
