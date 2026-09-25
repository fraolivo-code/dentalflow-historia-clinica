"""periodontograma: recesion_cairo, rangos, nivel de insercion calculado, furcacion por diente, unicidad

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-24

Modelo clinico confirmado con la Dra. (24/09/2026):
- recesion_cairo (RT1/RT2/RT3): columna nueva, nullable, adicional a recesion_mm.
- Rangos (red de seguridad, no clinicos): margen -6..12, sondaje 0..30, recesion 0..12.
  El sondaje puede superar 12 mm en casos reales (periodontitis severa); 30
  solo atrapa un typo evidente.
- nivel_insercion = margen_gingival + profundidad_sondaje: lo calcula el
  backend; el CHECK garantiza que nunca quede desfasado (tampoco tras un PATCH).
- furcacion solo en molares y en 14/24.
- Una sola carga por visita: UNIQUE (visita, diente, sitio) y (visita, diente).
Al momento de crearla ambas tablas tienen 0 filas en produccion.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

recesion_cairo = postgresql.ENUM("RT1", "RT2", "RT3", name="recesion_cairo")

CHECKS_REGISTRO = {
    "ck_perio_margen_gingival_rango": "margen_gingival BETWEEN -6 AND 12",
    "ck_perio_profundidad_sondaje_rango": "profundidad_sondaje BETWEEN 0 AND 30",
    "ck_perio_recesion_mm_rango": "recesion_mm BETWEEN 0 AND 12",
    "ck_perio_nivel_insercion_calculado": "nivel_insercion = margen_gingival + profundidad_sondaje",
}


def upgrade() -> None:
    recesion_cairo.create(op.get_bind(), checkfirst=False)
    op.add_column(
        "periodontograma_registro",
        sa.Column("recesion_cairo", recesion_cairo, nullable=True),
    )
    for nombre, condicion in CHECKS_REGISTRO.items():
        op.create_check_constraint(nombre, "periodontograma_registro", condicion)
    op.create_unique_constraint(
        "uq_perio_registro_visita_diente_sitio",
        "periodontograma_registro",
        ["visita_id", "numero_diente", "sitio"],
    )
    op.create_check_constraint(
        "ck_perio_furcacion_diente",
        "periodontograma_diente_resumen",
        "furcacion IS NULL OR numero_diente % 10 IN (6, 7, 8) OR numero_diente IN (14, 24)",
    )
    op.create_unique_constraint(
        "uq_perio_resumen_visita_diente",
        "periodontograma_diente_resumen",
        ["visita_id", "numero_diente"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_perio_resumen_visita_diente", "periodontograma_diente_resumen", type_="unique")
    op.drop_constraint("ck_perio_furcacion_diente", "periodontograma_diente_resumen", type_="check")
    op.drop_constraint("uq_perio_registro_visita_diente_sitio", "periodontograma_registro", type_="unique")
    for nombre in CHECKS_REGISTRO:
        op.drop_constraint(nombre, "periodontograma_registro", type_="check")
    op.drop_column("periodontograma_registro", "recesion_cairo")
    recesion_cairo.drop(op.get_bind(), checkfirst=False)
