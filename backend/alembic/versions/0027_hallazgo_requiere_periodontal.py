"""tipo_hallazgo: agrega requiere_periodontal (grupo "condicion")

Revision ID: 0027
Revises: 0026
Create Date: 2026-10-06

Decision de la Dra. (06/10/2026): marca "PER" en naranja junto al numero del
diente que requiere tratamiento periodontal sin cambiar su estado (corona,
perno, conducto). Solo agrega un valor al enum Postgres tipo_hallazgo; no toca
filas. La regla de grupo "condicion" vive en la aplicacion (app/enums.py).

ALTER TYPE ... ADD VALUE va en un bloque autocommit, igual que 0025.

downgrade: Postgres no permite quitar un valor de un enum; no-op a proposito.
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0027"
down_revision: Union[str, None] = "0026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE tipo_hallazgo ADD VALUE IF NOT EXISTS 'requiere_periodontal'")


def downgrade() -> None:
    pass
