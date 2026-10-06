"""tipo_hallazgo: agrega supernumerario (grupo "condicion")

Revision ID: 0025
Revises: 0024
Create Date: 2026-10-05

Decision de la Dra. (05/10/2026): un diente supernumerario no es un diente
concreto sino uno que se repite junto a otro; no se dibuja, se marca con "SN"
en rojo junto al numero del diente al que acompana. Solo agrega un valor al
enum Postgres tipo_hallazgo; no toca filas existentes. La regla de grupo
"condicion" (no cierra ni es cerrado por otro hallazgo) vive en la aplicacion
(app/enums.py).

ALTER TYPE ... ADD VALUE va en un bloque autocommit, igual que 0023.

downgrade: Postgres no permite quitar un valor de un enum; se deja como no-op
a proposito (igual que 0007).
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0025"
down_revision: Union[str, None] = "0024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE tipo_hallazgo ADD VALUE IF NOT EXISTS 'supernumerario'")


def downgrade() -> None:
    pass
