"""paciente.ultima_visita_odontologo: texto libre opcional, solo en el ingreso

Revision ID: 0026
Revises: 0025
Create Date: 2026-10-06

Pedido de la Dra./Francisco (06/10/2026): saber desde cuando el paciente no
visitaba al odontologo. Solo agrega una columna nullable; no toca filas.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0026"
down_revision: Union[str, None] = "0025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("paciente", sa.Column("ultima_visita_odontologo", sa.String(120), nullable=True))


def downgrade() -> None:
    op.drop_column("paciente", "ultima_visita_odontologo")
