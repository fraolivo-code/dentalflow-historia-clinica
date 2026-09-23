"""tipo_hallazgo: agrega diastema (grupo "condicion")

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-23

Solo agrega un valor al enum Postgres tipo_hallazgo; no toca filas
existentes. La regla de grupo "condicion" (no cierra ni es cerrado por
ningun otro hallazgo) y la superficie obligatoria mesial/distal viven en la
aplicacion (app/enums.py, app/services/odontograma_logic.py), no en la base.

downgrade: Postgres no permite quitar un valor de un enum. Revertir exigiria
recrear el tipo y reescribir las columnas que lo usan (odontograma_hallazgo,
bitacora_tratamiento, puente_fijo_diente), y fallaria si ya hay filas con
diastema — se deja como no-op a proposito.
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE tipo_hallazgo ADD VALUE IF NOT EXISTS 'diastema'")


def downgrade() -> None:
    pass
