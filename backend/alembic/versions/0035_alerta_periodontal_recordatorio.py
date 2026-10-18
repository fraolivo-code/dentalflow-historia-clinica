"""paciente: alerta, seguimiento periodontal, activo; tipo_visita reevaluacion; examen enlace; recordatorio

Revision ID: 0035
Revises: 0034
Create Date: 2026-10-17

Proceso de trabajo de la Dra. (docs/proceso-trabajo-caso-334.md, secciones 11 y 12).
- paciente.alerta / alerta_texto: la Dra. marca que el paciente requiere alerta y escribe de que se trata.
- paciente.seguimiento_periodontal / _texto: decide si se muestra el periodontograma.
- paciente.activo / motivo_inactivo: paciente que se da de baja (cambio de odontologo, etc.).
- tipo_visita: «reevaluacion».
- examen_solicitado.enlace: enlace a la Rx / tomografia (el archivo vive en el Drive de la Dra.).
- recordatorio: texto + fecha + hecho (proximo control, Rx pan para tal fecha, etc.).

Columnas con valor por defecto y tabla nueva: no se modifica ninguna fila existente.
ALTER TYPE ... ADD VALUE va en un bloque autocommit (igual que 0025, 0027, 0031 y 0034) y el valor
nuevo no se usa en esta migracion. downgrade: Postgres no permite quitar un valor de un enum
(no-op para ese valor).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0035"
down_revision: Union[str, None] = "0034"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE tipo_visita ADD VALUE IF NOT EXISTS 'reevaluacion'")

    op.add_column("paciente", sa.Column("alerta", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("paciente", sa.Column("alerta_texto", sa.Text(), nullable=True))
    op.add_column(
        "paciente", sa.Column("seguimiento_periodontal", sa.Boolean(), nullable=False, server_default=sa.false())
    )
    op.add_column("paciente", sa.Column("seguimiento_periodontal_texto", sa.Text(), nullable=True))
    op.add_column("paciente", sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("paciente", sa.Column("motivo_inactivo", sa.Text(), nullable=True))

    op.add_column("examen_solicitado", sa.Column("enlace", sa.String(1000), nullable=True))

    op.create_table(
        "recordatorio",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("paciente_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("paciente.id"), nullable=False),
        sa.Column("visita_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("visita.id"), nullable=True),
        sa.Column("texto", sa.Text(), nullable=False),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("hecho", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("hecho_fecha", sa.Date(), nullable=True),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("creado_por", postgresql.UUID(as_uuid=True), sa.ForeignKey("usuario.id"), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actualizado_por", postgresql.UUID(as_uuid=True), sa.ForeignKey("usuario.id"), nullable=True),
    )
    op.create_index("ix_recordatorio_paciente_id", "recordatorio", ["paciente_id"])
    op.create_index("ix_recordatorio_pendientes", "recordatorio", ["fecha"], postgresql_where=sa.text("NOT hecho"))


def downgrade() -> None:
    op.drop_index("ix_recordatorio_pendientes", table_name="recordatorio")
    op.drop_index("ix_recordatorio_paciente_id", table_name="recordatorio")
    op.drop_table("recordatorio")
    op.drop_column("examen_solicitado", "enlace")
    for columna in (
        "motivo_inactivo",
        "activo",
        "seguimiento_periodontal_texto",
        "seguimiento_periodontal",
        "alerta_texto",
        "alerta",
    ):
        op.drop_column("paciente", columna)
