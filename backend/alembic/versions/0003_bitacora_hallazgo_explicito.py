"""bitacora_tratamiento: tipo_hallazgo/superficie explicitos, para la regla
de creacion automatica del odontograma (seccion 7)

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-14
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# create_type=False: los tipos ya existen (creados en 0001), reutilizados tal
# cual en odontograma_hallazgo.
tipo_hallazgo = postgresql.ENUM(name="tipo_hallazgo", create_type=False)
superficie_dental = postgresql.ENUM(name="superficie_dental", create_type=False)


def upgrade() -> None:
    op.add_column("bitacora_tratamiento", sa.Column("tipo_hallazgo", tipo_hallazgo, nullable=True))
    op.add_column("bitacora_tratamiento", sa.Column("superficie", superficie_dental, nullable=True))


def downgrade() -> None:
    op.drop_column("bitacora_tratamiento", "superficie")
    op.drop_column("bitacora_tratamiento", "tipo_hallazgo")
