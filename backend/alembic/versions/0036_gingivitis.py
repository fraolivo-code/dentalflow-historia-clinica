"""odontograma: gingivitis (tipo_hallazgo) e implante rehabilitado / no rehabilitado

Revision ID: 0036
Revises: 0035
Create Date: 2026-10-18

Odontograma, criterio de la Dra. (docs/proceso-trabajo-caso-334.md): Gingivitis y Periodontitis en la
seccion Periodontales. Periodontitis es el antiguo «requiere_periodontal» (mismo valor guardado, otro
nombre en pantalla), asi que no hay datos que migrar.

odontograma_hallazgo.rehabilitado (boolean, por defecto true): los implantes que ya existen quedan
rehabilitados (tornillo + corona, como se dibujaban); «no rehabilitado» dibuja solo el tornillo.
Columna con valor por defecto: no se modifica ninguna fila.

ALTER TYPE ... ADD VALUE va en un bloque autocommit (igual que 0025, 0027, 0031, 0034 y 0035) y el valor
nuevo no se usa en esta migracion. downgrade: Postgres no permite quitar un valor de un enum; no-op.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0036"
down_revision: Union[str, None] = "0035"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE tipo_hallazgo ADD VALUE IF NOT EXISTS 'gingivitis'")
    op.add_column(
        "odontograma_hallazgo",
        sa.Column("rehabilitado", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column("odontograma_hallazgo", "rehabilitado")
    # Postgres no permite quitar un valor de un enum (gingivitis queda sin uso).
