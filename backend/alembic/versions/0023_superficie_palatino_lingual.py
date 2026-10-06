"""superficie_dental: agrega palatino_lingual

Revision ID: 0023
Revises: 0022
Create Date: 2026-10-05

Odontograma anatomico (decision de la Dra., 05/10/2026): una superficie nueva,
un solo valor, que se muestra como "Palatina" en los dientes superiores y
"Lingual" en los inferiores. Solo agrega un valor al enum Postgres
superficie_dental (usado por odontograma_hallazgo y bitacora_tratamiento); no
toca filas existentes. Que caries y obturaciones la admitan vive en la
aplicacion (SUPERFICIES_POR_TIPO en app/enums.py).

ALTER TYPE ... ADD VALUE no puede usarse en la misma transaccion donde se usa
el valor nuevo (y antes de Postgres 12 no corre dentro de una transaccion), por
eso va en un bloque autocommit: Alembic cierra la transaccion de la migracion,
corre el ALTER fuera de ella y abre otra para registrar la revision.

downgrade: Postgres no permite quitar un valor de un enum. Revertir exigiria
recrear el tipo y reescribir las columnas que lo usan. Por eso el downgrade
solo VERIFICA que ninguna fila use palatino_lingual (si hay alguna, falla y no
toca nada); el valor queda en el tipo, sin uso.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0023"
down_revision: Union[str, None] = "0022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Tablas con una columna superficie_dental.
TABLAS_CON_SUPERFICIE = ("odontograma_hallazgo", "bitacora_tratamiento")


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE superficie_dental ADD VALUE IF NOT EXISTS 'palatino_lingual'")


def downgrade() -> None:
    bind = op.get_bind()
    for tabla in TABLAS_CON_SUPERFICIE:
        usadas = bind.execute(
            sa.text(f"SELECT count(*) FROM {tabla} WHERE superficie = 'palatino_lingual'")
        ).scalar_one()
        if usadas:
            raise RuntimeError(
                f"No se puede revertir 0023: {tabla} tiene {usadas} fila(s) con superficie "
                "palatino_lingual (Postgres no permite quitar un valor de un enum). "
                "Cambie o elimine esas filas antes de revertir."
            )
