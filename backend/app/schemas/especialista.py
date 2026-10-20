# app/schemas/especialista.py — Lo que ve el especialista (19/10/2026). Cada respuesta es una LISTA BLANCA de campos:
# lo que no esta aqui (cedula, direccion, empresa, seguro, notas de visita sin dientes, recetas ajenas,
# constancias, consentimientos, presupuesto...) no sale del servidor aunque la pantalla lo ignore.
from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel

from app.enums import (
    Denticion,
    EstadoExamen,
    SuperficieDental,
    TipoExamen,
    TipoHallazgo,
    TipoLesionApical,
)


class PacienteDeEspecialista(BaseModel):
    """Una fila de «mis pacientes»."""

    id: UUID
    numero_historia: str
    nombre_completo: str
    edad: int | None
    movil: str
    email: str | None
    motivo: str
    remision_id: UUID
    remitido_en: datetime


class PacienteEspecialista(BaseModel):
    id: UUID
    numero_historia: str
    nombre_completo: str
    edad: int | None
    # Contacto: se comparte al remitir (decision de la Dra., 19/10/2026).
    movil: str
    telefono_fijo: str | None
    email: str | None
    alerta: bool
    alerta_texto: str | None
    fuma: bool
    fuma_detalle: str | None
    medicamentos_actuales: bool
    medicamentos_actuales_detalle: str | None
    tratamiento_medico_actual: str | None
    denticion: Denticion


class AntecedenteEspecialista(BaseModel):
    nombre: str
    detalle: str | None


class ExamenEspecialista(BaseModel):
    tipo: TipoExamen
    descripcion: str | None
    fecha_indicacion: date
    estado: EstadoExamen
    fecha_traido: date | None
    hallazgos: str | None
    enlace: str | None


class NotaEspecialista(BaseModel):
    """Nota ligada a dientes de la remision (las de «Dientes mencionados» y la bitacora por diente)."""

    fecha: date
    descripcion: str
    dientes: list[int]


class RemisionEspecialista(BaseModel):
    id: UUID
    motivo: str
    dientes: list[int]
    toda_la_boca: bool
    remitido_en: datetime


class FichaEspecialista(BaseModel):
    paciente: PacienteEspecialista
    remision: RemisionEspecialista
    antecedentes: list[AntecedenteEspecialista]
    examenes: list[ExamenEspecialista]
    notas: list[NotaEspecialista]


class HallazgoEspecialista(BaseModel):
    id: UUID
    numero_diente: int
    tipo_hallazgo: TipoHallazgo
    superficie: SuperficieDental | None
    fecha: date
    rehabilitado: bool


class LesionEspecialista(BaseModel):
    id: UUID
    numero_diente: int
    raiz: str
    tipo: TipoLesionApical
    fecha: date


class OdontogramaEspecialista(BaseModel):
    """Odontograma vigente, solo lectura."""

    hallazgos: list[HallazgoEspecialista]
    lesiones: list[LesionEspecialista]
