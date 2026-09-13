# app/models/common.py — Piezas compartidas por las tablas clinicas:
# PK en UUID y los 4 campos de auditoria de la seccion 0.1 del documento.
#
# creado_en / actualizado_en son el momento de transcripcion al sistema.
# NUNCA sustituyen al campo "fecha" propio de cada tabla clinica, que es el
# momento clinico real (lo que dice el papel) — ver seccion 0.1.

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column


def ahora() -> datetime:
    return datetime.now(timezone.utc)


class UUIDPk:
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )


class AuditMixin:
    """
    Campos de auditoria para toda tabla clinica (seccion 0.1). No se usa en
    `consentimiento`, que segun el documento solo lleva creado_en/creado_por
    (un consentimiento no se edita, se agrega uno nuevo), ni en
    `diente_anatomia`, que es catalogo estatico sin trazabilidad clinica.
    """

    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=ahora, nullable=False
    )
    creado_por: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("usuario.id"), nullable=False
    )
    actualizado_en: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    actualizado_por: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("usuario.id"), nullable=True
    )
