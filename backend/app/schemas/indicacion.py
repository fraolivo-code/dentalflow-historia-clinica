from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from app.schemas.common import AuditRead


def _limpiar(v: str | None) -> str | None:
    """Recorta espacios sobrantes; en blanco equivale a no enviado."""
    if v is None:
        return None
    v = v.strip()
    return v or None


# --- Catalogo de plantillas ---------------------------------------------------

class PlantillaIndicacionCreate(BaseModel):
    nombre: str
    tipo_tratamiento: str | None = None
    contenido: str

    _limpiar_textos = field_validator("nombre", "tipo_tratamiento", "contenido")(_limpiar)

    @model_validator(mode="after")
    def _obligatorios(self) -> "PlantillaIndicacionCreate":
        vacios = [c for c in ("nombre", "contenido") if getattr(self, c) is None]
        if vacios:
            raise ValueError(f"No pueden quedar vacios: {', '.join(vacios)}")
        return self


class PlantillaIndicacionUpdate(BaseModel):
    """Actualizacion parcial (exclude_unset en el router)."""

    nombre: str | None = None
    tipo_tratamiento: str | None = None
    contenido: str | None = None

    _limpiar_textos = field_validator("nombre", "tipo_tratamiento", "contenido")(_limpiar)

    @model_validator(mode="after")
    def _validar(self) -> "PlantillaIndicacionUpdate":
        if not self.model_fields_set:
            raise ValueError("No hay ningun campo para corregir")
        vacios = sorted(
            c for c in ("nombre", "contenido") if c in self.model_fields_set and getattr(self, c) is None
        )
        if vacios:
            raise ValueError(f"No pueden quedar vacios: {', '.join(vacios)}")
        return self


class PlantillaIndicacionRead(AuditRead):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    nombre: str
    tipo_tratamiento: str | None
    contenido: str


# --- Indicacion entregada al paciente -------------------------------------------

class IndicacionTratamientoCreate(BaseModel):
    # emitida_por NO se acepta del cliente: sale del profesional vinculado al
    # usuario autenticado.
    plantilla_id: UUID | None = None
    # Sin contenido_final se precarga el de la plantilla; si viene, se usa tal
    # cual (la Dra. pudo haberlo editado).
    contenido_final: str | None = None
    visita_id: UUID | None = None
    tratamiento_id: UUID | None = None
    fecha: date | None = None  # None = hoy (hora de Venezuela)

    _limpiar_contenido = field_validator("contenido_final")(_limpiar)

    @model_validator(mode="after")
    def _con_contenido(self) -> "IndicacionTratamientoCreate":
        if self.plantilla_id is None and self.contenido_final is None:
            raise ValueError("Se necesita plantilla_id o contenido_final")
        return self


class IndicacionTratamientoRead(AuditRead):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    paciente_id: UUID
    visita_id: UUID | None
    tratamiento_id: UUID | None
    plantilla_id: UUID | None
    contenido_final: str
    fecha: date
    emitida_por: UUID
