from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

from app.enums import EstadoTratamiento, OrigenTratamiento, NUMEROS_DIENTE_VALIDOS
from app.schemas.common import AuditRead


class TratamientoCreate(BaseModel):
    tipo: str
    estado: EstadoTratamiento = EstadoTratamiento.indicado
    origen: OrigenTratamiento = OrigenTratamiento.aqui
    origen_detalle: str | None = None
    fecha_inicio: date
    fecha_fin: date | None = None
    profesional_tratante_id: UUID
    notas_relevantes: str | None = None
    # Dientes involucrados (seccion 6, tratamiento_diente). Vacio si el
    # tratamiento no aplica a dientes puntuales.
    dientes: list[int] = []

    @field_validator("dientes")
    @classmethod
    def _validar_dientes(cls, v: list[int]) -> list[int]:
        for numero in v:
            if numero not in NUMEROS_DIENTE_VALIDOS:
                raise ValueError(f"{numero} no es un numero de diente valido (notacion FDI)")
        return v


class TratamientoUpdate(BaseModel):
    """
    Actualizacion parcial del ciclo de vida (indicado -> en_curso ->
    completado/suspendido) — no reemplaza dientes ni datos de origen.
    """

    estado: EstadoTratamiento | None = None
    fecha_fin: date | None = None
    notas_relevantes: str | None = None


class TratamientoDienteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    numero_diente: int


class TratamientoRead(AuditRead):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    paciente_id: UUID
    tipo: str
    estado: EstadoTratamiento
    origen: OrigenTratamiento
    origen_detalle: str | None
    fecha_inicio: date
    fecha_fin: date | None
    profesional_tratante_id: UUID
    notas_relevantes: str | None
    dientes: list[int]
