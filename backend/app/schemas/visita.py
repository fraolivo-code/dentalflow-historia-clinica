from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.enums import HigieneBucal
from app.schemas.common import AuditRead


class VisitaCreate(BaseModel):
    # responsable y creado_por ya NO se aceptan del cliente (19/09/2026): el
    # unico rol con acceso a este endpoint hoy es dra, asi que ambos se
    # derivan del usuario autenticado (JWT) — ver "Nota" en visitas.py.
    fecha: date
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
    examen_tomografia: bool = False
    examen_otras: str | None = None
    hallazgos: str | None = None


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
    examen_tomografia: bool
    examen_otras: str | None
    hallazgos: str | None
