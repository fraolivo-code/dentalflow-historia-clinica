# app/models/profesional_tratante.py — Etapa 3, seccion 6. Catalogo editable,
# distinto de `usuario`: a quien se le atribuye la ejecucion clinica de un
# tratamiento (la propia Dra., o un especialista externo al que se remite).
# Texto libre al transcribir (papel -> digital), no un desplegable cerrado
# — ver principio de diseno en la seccion 6 de la especificacion.

import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.common import UUIDPk


class ProfesionalTratante(Base, UUIDPk):
    __tablename__ = "profesional_tratante"

    nombre: Mapped[str] = mapped_column(String(300), nullable=False)
    especialidad: Mapped[str | None] = mapped_column(String(300), nullable=True)
    # Se imprime en receta y constancia (formato legal). Nullable hasta tener
    # el dato real de cada profesional.
    numero_colegiatura: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Cuenta de acceso que firma como este profesional (25/09/2026): de aca
    # sale emitida_por de los documentos, nunca del body. Null para los
    # especialistas externos, que no tienen cuenta en el sistema.
    usuario_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("usuario.id"), nullable=True, unique=True
    )
