"""puente_fijo: resuelto / resuelto_fecha; CHECK rol <-> condicion_individual

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-24

Mismo patron que odontograma_lesion_apical (0008): un puente se cierra sin
borrarse (PATCH /pacientes/{id}/puentes/{id}/resolver). El CHECK nuevo de
puente_fijo_diente es la capa 3 de la regla rol <-> condicion (24/09/2026):
un pontico es un diente ausente por definicion, y un pilar nunca lo es.
Al momento de crearla ambas tablas tienen 0 filas en produccion.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "puente_fijo",
        sa.Column("resuelto", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column("puente_fijo", "resuelto", server_default=None)
    op.add_column("puente_fijo", sa.Column("resuelto_fecha", sa.Date(), nullable=True))
    op.create_check_constraint(
        "ck_puente_fijo_diente_rol_condicion",
        "puente_fijo_diente",
        "(rol = 'pontico') = (condicion_individual = 'ausente')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_puente_fijo_diente_rol_condicion", "puente_fijo_diente", type_="check")
    op.drop_column("puente_fijo", "resuelto_fecha")
    op.drop_column("puente_fijo", "resuelto")
