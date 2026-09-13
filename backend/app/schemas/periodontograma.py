from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

from app.enums import FurcacionGlickman, SitioPeriodontal
from app.schemas.common import AuditRead, NumeroDienteValidoMixin


class PeriodontogramaRegistroCreate(NumeroDienteValidoMixin):
    numero_diente: int
    sitio: SitioPeriodontal
    margen_gingival: int
    profundidad_sondaje: int
    nivel_insercion: int
    recesion_mm: int = 0
    sangrado: bool = False
    placa: bool = False


class PeriodontogramaRegistroRead(AuditRead):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    paciente_id: UUID
    visita_id: UUID
    numero_diente: int
    sitio: SitioPeriodontal
    margen_gingival: int
    profundidad_sondaje: int
    nivel_insercion: int
    recesion_mm: int
    sangrado: bool
    placa: bool


class PeriodontogramaDienteResumenCreate(NumeroDienteValidoMixin):
    numero_diente: int
    movilidad: int
    furcacion: FurcacionGlickman | None = None

    @field_validator("movilidad")
    @classmethod
    def _movilidad_en_rango(cls, v: int) -> int:
        if not 0 <= v <= 3:
            raise ValueError("movilidad debe estar entre 0 y 3 (escala Miller)")
        return v


class PeriodontogramaDienteResumenRead(AuditRead):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    paciente_id: UUID
    visita_id: UUID
    numero_diente: int
    movilidad: int
    furcacion: FurcacionGlickman | None


class PeriodontogramaVisitaCreate(BaseModel):
    """Carga completa de un levantamiento periodontal para una visita."""

    creado_por: UUID
    registros: list[PeriodontogramaRegistroCreate]
    resumenes: list[PeriodontogramaDienteResumenCreate]


class PeriodontogramaVisitaRead(BaseModel):
    registros: list[PeriodontogramaRegistroRead]
    resumenes: list[PeriodontogramaDienteResumenRead]
