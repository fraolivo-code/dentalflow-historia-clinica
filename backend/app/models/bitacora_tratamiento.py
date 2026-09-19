# app/models/bitacora_tratamiento.py — Entrada fechada del plan de
# tratamiento. No tiene tabla de campos propia en ningun documento (a
# diferencia del resto del esquema): se reconstruye a partir de lo acordado
# en proceso-automatizacion-odontologo-v2.md ("bitacora fechada, no un solo
# campo de texto" + columna "Responsable" confirmada) mas la regla de vinculo
# con el odontograma (especificacion-tecnica-formularios-fase2.md, seccion 7).
#
# numero_diente y tratamiento_id quedan nullable: hay entradas de un solo
# evento (ej. "limpieza simple") que no pertenecen a un diente puntual ni a
# un tratamiento multisesion.
#
# tipo_hallazgo / superficie: la Dra. los llena explicitamente en el mismo
# formulario de bitacora (igual que ya elige un hallazgo en la pantalla del
# odontograma) — no se infieren del texto de `descripcion`. Cuando
# numero_diente y tipo_hallazgo vienen ambos llenos, la API crea
# automaticamente la fila correspondiente en odontograma_hallazgo (seccion 7
# de la especificacion de formularios). Reutilizan los mismos enums nativos
# de odontograma_hallazgo (create_type=False: el tipo ya existe en Postgres).

import uuid
from datetime import date

from sqlalchemy import Date, Enum, ForeignKey, SmallInteger, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.enums import SuperficieDental, TipoHallazgo
from app.models.common import AuditMixin, UUIDPk


class BitacoraTratamiento(Base, UUIDPk, AuditMixin):
    __tablename__ = "bitacora_tratamiento"

    paciente_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("paciente.id"), nullable=False, index=True
    )
    visita_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("visita.id"), nullable=True
    )
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    responsable: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("usuario.id"), nullable=False
    )
    descripcion: Mapped[str] = mapped_column(Text, nullable=False)
    numero_diente: Mapped[int | None] = mapped_column(
        SmallInteger, ForeignKey("diente_anatomia.numero_diente"), nullable=True, index=True
    )
    # Nullable: no toda entrada pertenece a un tratamiento multisesion.
    tratamiento_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tratamiento.id"), nullable=True, index=True
    )
    tipo_hallazgo: Mapped[TipoHallazgo | None] = mapped_column(
        Enum(TipoHallazgo, name="tipo_hallazgo", native_enum=True, create_type=False),
        nullable=True,
    )
    superficie: Mapped[SuperficieDental | None] = mapped_column(
        Enum(SuperficieDental, name="superficie_dental", native_enum=True, create_type=False),
        nullable=True,
    )
