"""paciente.estado_historia: historia en carga / aprobada

Revision ID: 0033
Revises: 0032
Create Date: 2026-10-15

Procedimiento de carga acordado con la Dra. (15/10/2026): las historias de papel las carga
Francisco fuera de consulta y bajo su supervision; mientras tanto estan «en carga» (se pueden
corregir y eliminar, y lo que se imprime sale como BORRADOR) y la Dra. las aprueba al terminar
la revision. Las fichas que YA existen quedan «aprobada»; las nuevas nacen «en_carga».
Enum y dos columnas nuevas: no toca el resto de las filas.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0033"
down_revision: Union[str, None] = "0032"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_VALORES = ("en_carga", "aprobada")


def upgrade() -> None:
    postgresql.ENUM(*_VALORES, name="estado_historia").create(op.get_bind(), checkfirst=True)
    # Las filas existentes quedan aprobadas; el default para las nuevas es en_carga.
    op.add_column(
        "paciente",
        sa.Column(
            "estado_historia",
            postgresql.ENUM(*_VALORES, name="estado_historia", create_type=False),
            nullable=False,
            server_default="aprobada",
        ),
    )
    op.alter_column("paciente", "estado_historia", server_default="en_carga")
    op.add_column("paciente", sa.Column("aprobada_en", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "paciente",
        sa.Column("aprobada_por", postgresql.UUID(as_uuid=True), sa.ForeignKey("usuario.id"), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("paciente", "aprobada_por")
    op.drop_column("paciente", "aprobada_en")
    op.drop_column("paciente", "estado_historia")
    postgresql.ENUM(name="estado_historia").drop(op.get_bind(), checkfirst=True)
