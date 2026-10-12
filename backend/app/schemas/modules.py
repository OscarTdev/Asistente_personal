"""Schemas para el sistema de módulos."""

from pydantic import BaseModel, ConfigDict, Field


class ModuleInfo(BaseModel):
    """Información de un módulo + su estado en el tenant actual."""

    model_config = ConfigDict(from_attributes=True)

    key: str
    name: str
    description: str | None = None
    category: str
    is_enabled: bool
    is_custom: bool = False
    dev_status: str = "development"
    workspace: str | None = None


class ModuleToggle(BaseModel):
    """Payload para activar o desactivar un módulo."""

    is_enabled: bool


class ModuleCreate(BaseModel):
    """Payload para registrar un nuevo módulo para el tenant."""

    name: str = Field(..., min_length=2, max_length=100)
    key: str | None = Field(None, min_length=2, max_length=50)
    description: str | None = Field(None, max_length=1000)
    category: str = Field("personalizado", max_length=50)


class ModuleUpdate(BaseModel):
    """Payload para actualizar datos de un módulo existente."""

    name: str | None = Field(None, min_length=2, max_length=100)
    description: str | None = Field(None, max_length=1000)
    category: str | None = Field(None, max_length=50)
    is_enabled: bool | None = None
