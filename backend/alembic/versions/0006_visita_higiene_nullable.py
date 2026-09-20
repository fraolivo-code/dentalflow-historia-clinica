"""visita: higiene pasa a nullable (visita liviana de asistente)

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-20

El tipo Postgres higiene_bucal no cambia (sigue E/B/R/M/P) — solo se retira
el NOT NULL de la columna, para permitir crear una visita liviana (solo
fecha + motivo_consulta) desde el rol asistente y completar el examen
clinico despues via PATCH /visitas/{id} (confirmado 20/09/2026).
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("visita", "higiene", nullable=True)


def downgrade() -> None:
    op.alter_column("visita", "higiene", nullable=False)
