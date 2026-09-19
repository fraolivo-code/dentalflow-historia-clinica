# app/models/__init__.py — Importa todos los modelos para que
# Base.metadata (app/db.py) los conozca (usado por Alembic autogenerate y por
# cualquier create_all en tests).

from app.models.antecedente import Antecedente, PacienteAntecedente
from app.models.bitacora_tratamiento import BitacoraTratamiento
from app.models.consentimiento import Consentimiento
from app.models.observacion import Observacion
from app.models.odontograma import (
    DienteAnatomia,
    OdontogramaHallazgo,
    OdontogramaLesionApical,
    PuenteFijo,
    PuenteFijoDiente,
)
from app.models.paciente import Paciente
from app.models.periodontograma import PeriodontogramaDienteResumen, PeriodontogramaRegistro
from app.models.profesional_tratante import ProfesionalTratante
from app.models.tratamiento import Tratamiento, TratamientoDiente
from app.models.usuario import Usuario
from app.models.visita import Visita

__all__ = [
    "Antecedente",
    "BitacoraTratamiento",
    "Consentimiento",
    "DienteAnatomia",
    "Observacion",
    "OdontogramaHallazgo",
    "OdontogramaLesionApical",
    "PacienteAntecedente",
    "PuenteFijo",
    "PuenteFijoDiente",
    "Paciente",
    "PeriodontogramaDienteResumen",
    "PeriodontogramaRegistro",
    "ProfesionalTratante",
    "Tratamiento",
    "TratamientoDiente",
    "Usuario",
    "Visita",
]
