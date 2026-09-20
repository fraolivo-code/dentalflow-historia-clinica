"""etapa 3: secuencia de numero_historia y extension unaccent para busqueda

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-20

numero_historia deja de venir del cliente (ver schemas/paciente.py) y pasa a
generarse server-side con esta secuencia — atomica, sin condicion de carrera
posible aunque dra y asistente creen pacientes al mismo tiempo.

unaccent permite que la busqueda de pacientes (GET /pacientes?q=) ignore
acentos ademas de mayusculas/minusculas.
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")
    op.execute("CREATE SEQUENCE IF NOT EXISTS paciente_numero_historia_seq START WITH 1")


def downgrade() -> None:
    op.execute("DROP SEQUENCE IF EXISTS paciente_numero_historia_seq")
    op.execute("DROP EXTENSION IF EXISTS unaccent")
