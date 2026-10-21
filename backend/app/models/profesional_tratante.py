# app/models/profesional_tratante.py — Etapa 3, seccion 6. Catalogo editable,
# distinto de `usuario`: a quien se le atribuye la ejecucion clinica de un
# tratamiento (la propia Dra., o un especialista externo al que se remite).
# Texto libre al transcribir (papel -> digital), no un desplegable cerrado
# — ver principio de diseno en la seccion 6 de la especificacion.

import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.common import UUIDPk


class ProfesionalTratante(Base, UUIDPk):
    __tablename__ = "profesional_tratante"

    nombre: Mapped[str] = mapped_column(String(300), nullable=False)
    especialidad: Mapped[str | None] = mapped_column(String(300), nullable=True)
    # Dato antiguo en un solo texto («C.O.V. 15766 - M.S.D.S. 15491»). Desde la migracion 0039 se usan `cov` y
    # `mpps`; este queda solo como respaldo para profesionales que aun no los tengan.
    numero_colegiatura: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Membrete de los documentos (migracion 0039, 20/10/2026). COV y MPPS son obligatorios para emitir recetas.
    direccion: Mapped[str | None] = mapped_column(Text, nullable=True)
    telefonos: Mapped[str | None] = mapped_column(String(300), nullable=True)
    correo: Mapped[str | None] = mapped_column(String(254), nullable=True)
    rif: Mapped[str | None] = mapped_column(String(30), nullable=True)
    cov: Mapped[str | None] = mapped_column(String(50), nullable=True)
    mpps: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # Cuenta de acceso que firma como este profesional (25/09/2026): de aca
    # sale emitida_por de los documentos, nunca del body. Null para los
    # especialistas externos, que no tienen cuenta en el sistema.
    usuario_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("usuario.id"), nullable=True, unique=True
    )
