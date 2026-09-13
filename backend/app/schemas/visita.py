from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.enums import HigieneBucal
from app.schemas.common import AuditRead


class VisitaCreate(BaseModel):
    fecha: date
    responsable: UUID
    motivo_consulta: str | None = None
    examen_extraoral_atm: str | None = None
    examen_extraoral_ganglios: str | None = None
    examen_extraoral_otros: str | None = None
    higiene: HigieneBucal
    tejidos_blandos: str | None = None
    examen_rx_periapical: bool = False
    examen_ex_pc: bool = False
    examen_rx_panoramica: bool = False
    examen_rutina_quirurgica: bool = False
    examen_otras: str | None = None
    hallazgos: str | None = None
    creado_por: UUID


class VisitaRead(AuditRead):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    paciente_id: UUID
    fecha: date
    responsable: UUID
    motivo_consulta: str | None
    examen_extraoral_atm: str | None
    examen_extraoral_ganglios: str | None
    examen_extraoral_otros: str | None
    higiene: HigieneBucal
    tejidos_blandos: str | None
    examen_rx_periapical: bool
    examen_ex_pc: bool
    examen_rx_panoramica: bool
    examen_rutina_quirurgica: bool
    examen_otras: str | None
    hallazgos: str | None
