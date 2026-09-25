"""paciente: cedula (nullable)

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-25

Pedido para la constancia de asistencia (uso laboral: el empleador verifica
identidad). Opcional y sin UNIQUE: numero_historia sigue siendo la
identificacion del paciente (hay menores sin documento), y los pacientes ya
cargados quedan sin cedula hasta que se complete.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("paciente", sa.Column("cedula", sa.String(20), nullable=True))


def downgrade() -> None:
    op.drop_column("paciente", "cedula")
