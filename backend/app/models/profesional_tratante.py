# app/models/profesional_tratante.py — Etapa 3, seccion 6. Catalogo editable,
# distinto de `usuario`: a quien se le atribuye la ejecucion clinica de un
# tratamiento (la propia Dra., o un especialista externo al que se remite).
# Texto libre al transcribir (papel -> digital), no un desplegable cerrado
# — ver principio de diseno en la seccion 6 de la especificacion.

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.common import UUIDPk


class ProfesionalTratante(Base, UUIDPk):
    __tablename__ = "profesional_tratante"

    nombre: Mapped[str] = mapped_column(String(300), nullable=False)
    especialidad: Mapped[str | None] = mapped_column(String(300), nullable=True)
