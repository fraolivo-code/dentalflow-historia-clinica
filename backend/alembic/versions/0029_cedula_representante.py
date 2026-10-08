"""paciente.cedula_representante: cedula del padre/madre/tutor de un menor

Revision ID: 0029
Revises: 0028
Create Date: 2026-10-08

Pedido de la Dra. (08/10/2026): segundo dato para ubicar a un menor sin cedula.
Solo agrega una columna nullable; no toca filas ni es unica (hermanos).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0029"
down_revision: Union[str, None] = "0028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("paciente", sa.Column("cedula_representante", sa.String(20), nullable=True))


def downgrade() -> None:
    op.drop_column("paciente", "cedula_representante")
