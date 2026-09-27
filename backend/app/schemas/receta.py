from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.common import AuditRead
from app.schemas.indicacion import _limpiar


# --- Catalogo de medicamentos ---------------------------------------------------

class MedicamentoCreate(BaseModel):
    nombre: str
    presentacion_default: str | None = None
    es_favorito: bool = False

    _limpiar_textos = field_validator("nombre", "presentacion_default")(_limpiar)

    @model_validator(mode="after")
    def _con_nombre(self) -> "MedicamentoCreate":
        if self.nombre is None:
            raise ValueError("El nombre no puede quedar vacio")
        return self


class MedicamentoUpdate(BaseModel):
    """Actualizacion parcial (exclude_unset en el router)."""

    nombre: str | None = None
    presentacion_default: str | None = None
    es_favorito: bool | None = None

    _limpiar_textos = field_validator("nombre", "presentacion_default")(_limpiar)

    @model_validator(mode="after")
    def _validar(self) -> "MedicamentoUpdate":
        if not self.model_fields_set:
            raise ValueError("No hay ningun campo para corregir")
        if "nombre" in self.model_fields_set and self.nombre is None:
            raise ValueError("El nombre no puede quedar vacio")
        if "es_favorito" in self.model_fields_set and self.es_favorito is None:
            raise ValueError("es_favorito debe ser true o false")
        return self


class MedicamentoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    nombre: str
    presentacion_default: str | None
    es_favorito: bool


# --- Receta -----------------------------------------------------------------------

class RecetaMedicamentoCreate(BaseModel):
    # Uno de los dos: id del catalogo, o texto libre (se agrega al catalogo si
    # no existe un medicamento con ese nombre).
    medicamento_id: UUID | None = None
    medicamento_nombre: str | None = None
    dosis: str
    via: str | None = None
    frecuencia: str
    duracion: str
    indicaciones_adicionales: str | None = None

    _limpiar_textos = field_validator(
        "medicamento_nombre", "dosis", "via", "frecuencia", "duracion", "indicaciones_adicionales"
    )(_limpiar)

    @model_validator(mode="after")
    def _validar(self) -> "RecetaMedicamentoCreate":
        if (self.medicamento_id is None) == (self.medicamento_nombre is None):
            raise ValueError("Cada linea necesita medicamento_id o medicamento_nombre (uno solo)")
        vacios = [c for c in ("dosis", "frecuencia", "duracion") if getattr(self, c) is None]
        if vacios:
            raise ValueError(f"No pueden quedar vacios: {', '.join(vacios)}")
        return self


class RecetaCreate(BaseModel):
    # emitida_por NO se acepta del cliente: sale del profesional vinculado al
    # usuario autenticado.
    visita_id: UUID | None = None
    tratamiento_id: UUID | None = None
    fecha: date | None = None  # None = hoy (hora de Venezuela)
    notas_generales: str | None = None
    # Una receta sin medicamentos no tiene sentido: vacia -> 422.
    medicamentos: list[RecetaMedicamentoCreate] = Field(min_length=1)

    _limpiar_notas = field_validator("notas_generales")(_limpiar)


class RecetaMedicamentoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    orden: int
    # Referencia al catalogo (estado actual) + lo que quedo impreso al emitir.
    medicamento: MedicamentoRead
    medicamento_nombre_impreso: str
    presentacion_impresa: str | None
    dosis: str
    via: str | None
    frecuencia: str
    duracion: str
    indicaciones_adicionales: str | None


class RecetaRead(AuditRead):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    paciente_id: UUID
    visita_id: UUID | None
    tratamiento_id: UUID | None
    fecha: date
    notas_generales: str | None
    emitida_por: UUID
    medicamentos: list[RecetaMedicamentoRead]
