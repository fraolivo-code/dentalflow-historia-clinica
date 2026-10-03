"""tabla consulta_vinculacion (registro de consultas de Alma, Etapa 6)

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-02

Fecha, endpoint, movil normalizado consultado y resultado. No guarda el
nombre escrito por la persona. Retencion de 90 dias (purga perezosa en
app/services/vinculacion.py).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0017"
down_revision: Union[str, None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "consulta_vinculacion",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("fecha", sa.DateTime(timezone=True), nullable=False),
        sa.Column("endpoint", sa.String(50), nullable=False),
        sa.Column("movil_normalizado", sa.String(15), nullable=True),
        sa.Column("resultado", sa.String(20), nullable=False),
    )
    op.create_index("ix_consulta_vinculacion_fecha", "consulta_vinculacion", ["fecha"])


def downgrade() -> None:
    op.drop_index("ix_consulta_vinculacion_fecha", table_name="consulta_vinculacion")
    op.drop_table("consulta_vinculacion")
