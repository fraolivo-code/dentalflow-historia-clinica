"""periodontograma: nivel de insercion = profundidad de sondaje - margen gingival

Revision ID: 0024
Revises: 0023
Create Date: 2026-10-05

Correccion clinica: la Dra. anota el margen gingival en NEGATIVO cuando hay
recesion (convencion de la Universidad de Berna / perio-tools.com), asi que
NI = PS - MG (antes se calculaba MG + PS).

- Reemplaza el CHECK ck_perio_nivel_insercion_calculado.
- Recalcula nivel_insercion de TODAS las filas existentes con la formula nueva
  (primero se quita el CHECK viejo y al final se pone el nuevo).
- Rangos sin cambio: margen -6..12, sondaje 0..30. NI queda en -12..36, que
  cabe en SmallInteger y no tiene CHECK de rango propio.

Reversible: el downgrade restaura la formula MG + PS y recalcula las filas
(los valores de MG y PS no se tocan en ningun sentido).
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0024"
down_revision: Union[str, None] = "0023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLA = "periodontograma_registro"
CHECK = "ck_perio_nivel_insercion_calculado"


def _cambiar(formula_check: str, formula_valor: str) -> None:
    with op.batch_alter_table(TABLA) as lote:
        lote.drop_constraint(CHECK, type_="check")
    op.execute(f"UPDATE {TABLA} SET nivel_insercion = {formula_valor}")
    with op.batch_alter_table(TABLA) as lote:
        lote.create_check_constraint(CHECK, formula_check)


def upgrade() -> None:
    _cambiar("nivel_insercion = profundidad_sondaje - margen_gingival", "profundidad_sondaje - margen_gingival")


def downgrade() -> None:
    _cambiar("nivel_insercion = margen_gingival + profundidad_sondaje", "margen_gingival + profundidad_sondaje")
