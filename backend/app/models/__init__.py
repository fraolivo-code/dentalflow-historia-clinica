# app/models/__init__.py — Importa todos los modelos para que
# Base.metadata (app/db.py) los conozca (usado por Alembic autogenerate y por
# cualquier create_all en tests).

from app.models.consentimiento import Consentimiento
from app.models.odontograma import (
    DienteAnatomia,
    OdontogramaHallazgo,
    OdontogramaLesionApical,
    PuenteFijo,
    PuenteFijoDiente,
)
from app.models.paciente import Paciente
from app.models.periodontograma import PeriodontogramaDienteResumen, PeriodontogramaRegistro
from app.models.usuario import Usuario
from app.models.visita import Visita

__all__ = [
    "Consentimiento",
    "DienteAnatomia",
    "OdontogramaHallazgo",
    "OdontogramaLesionApical",
    "PuenteFijo",
    "PuenteFijoDiente",
    "Paciente",
    "PeriodontogramaDienteResumen",
    "PeriodontogramaRegistro",
    "Usuario",
    "Visita",
]
