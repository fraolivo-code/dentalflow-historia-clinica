"""paciente_cambio: historial de correcciones de los datos del paciente

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-04

Una fila por campo realmente corregido (quien, cuando, campo, valor anterior y
nuevo como texto). Es parte del registro de la historia clinica: sin retencion
automatica. Reversible: el downgrade borra la tabla (y con ella el historial).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0021"
down_revision: Union[str, None] = "0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "paciente_cambio",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "paciente_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("paciente.id"),
            nullable=False,
        ),
        sa.Column("fecha", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "actor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("usuario.id"), nullable=False
        ),
        sa.Column("campo", sa.String(60), nullable=False),
        sa.Column("valor_anterior", sa.Text(), nullable=True),
        sa.Column("valor_nuevo", sa.Text(), nullable=True),
    )
    op.create_index("ix_paciente_cambio_paciente_id", "paciente_cambio", ["paciente_id"])


def downgrade() -> None:
    op.drop_index("ix_paciente_cambio_paciente_id", table_name="paciente_cambio")
    op.drop_table("paciente_cambio")
