"""examen_solicitado: examenes que la Dra. indica y el paciente trae

Revision ID: 0032
Revises: 0031
Create Date: 2026-10-15

Flujo de visitas, fase 3 (especificacion-tecnica-flujo-visitas-tratamientos.md, seccion 7).
Decision de la Dra.: la radiografia o tomografia se indica; cuando el paciente la trae
se registra que la trajo y los hallazgos si existen (sin guardar la imagen).
Tabla nueva y dos enums nuevos: no toca filas.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0032"
down_revision: Union[str, None] = "0031"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TIPOS = ("rx_periapical", "rx_panoramica", "tomografia", "otro")
_ESTADOS = ("indicado", "traido")


def upgrade() -> None:
    postgresql.ENUM(*_TIPOS, name="tipo_examen").create(op.get_bind(), checkfirst=True)
    postgresql.ENUM(*_ESTADOS, name="estado_examen").create(op.get_bind(), checkfirst=True)
    op.create_table(
        "examen_solicitado",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("paciente_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("paciente.id"), nullable=False),
        sa.Column("visita_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("visita.id"), nullable=True),
        sa.Column("tratamiento_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tratamiento.id"), nullable=True),
        sa.Column("tipo", postgresql.ENUM(*_TIPOS, name="tipo_examen", create_type=False), nullable=False),
        sa.Column("descripcion", sa.String(300), nullable=True),
        sa.Column("fecha_indicacion", sa.Date(), nullable=False),
        sa.Column("estado", postgresql.ENUM(*_ESTADOS, name="estado_examen", create_type=False), nullable=False),
        sa.Column("fecha_traido", sa.Date(), nullable=True),
        sa.Column("hallazgos", sa.Text(), nullable=True),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("creado_por", postgresql.UUID(as_uuid=True), sa.ForeignKey("usuario.id"), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actualizado_por", postgresql.UUID(as_uuid=True), sa.ForeignKey("usuario.id"), nullable=True),
    )
    op.create_index("ix_examen_solicitado_paciente_id", "examen_solicitado", ["paciente_id"])


def downgrade() -> None:
    op.drop_index("ix_examen_solicitado_paciente_id", table_name="examen_solicitado")
    op.drop_table("examen_solicitado")
    postgresql.ENUM(name="estado_examen").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="tipo_examen").drop(op.get_bind(), checkfirst=True)
