"""tipo_hallazgo: perno_ok, perno_defecto, sellante, cambio_coloracion

Revision ID: 0031
Revises: 0030
Create Date: 2026-10-15

Flujo de visitas, fase 2 (especificacion-tecnica-flujo-visitas-tratamientos.md, seccion 6).
Decisiones de la Dra. (08 y 14/10/2026): el conducto y el perno son dos cosas separadas;
sellante aplicado con la sigla SELL en azul; cambio de coloracion con la sigla CC en marron.
Solo agrega valores al enum Postgres tipo_hallazgo; no toca filas. La regla de grupo
(independiente / condicion) vive en la aplicacion (app/enums.py).

ALTER TYPE ... ADD VALUE va en un bloque autocommit, igual que 0025 y 0027.

downgrade: Postgres no permite quitar un valor de un enum; no-op a proposito.
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0031"
down_revision: Union[str, None] = "0030"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NUEVOS = ("perno_ok", "perno_defecto", "sellante", "cambio_coloracion")


def upgrade() -> None:
    with op.get_context().autocommit_block():
        for valor in _NUEVOS:
            op.execute(f"ALTER TYPE tipo_hallazgo ADD VALUE IF NOT EXISTS '{valor}'")


def downgrade() -> None:
    pass
