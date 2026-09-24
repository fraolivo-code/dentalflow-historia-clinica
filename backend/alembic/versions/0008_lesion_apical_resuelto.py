"""odontograma_lesion_apical: resuelto / resuelto_fecha / resuelto_por_hallazgo_id

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-23

Mismo patron que odontograma_hallazgo (0002, seccion 7): una lesion apical
se cierra sin borrarse. resuelto_por_hallazgo_id es NULL en un cierre manual
(PATCH /pacientes/{id}/lesiones-apicales/{id}/resolver) y apunta al hallazgo
que la cerro en un cierre automatico (implante/ausente, confirmado 23/09/2026).
Al momento de crearla la tabla tiene 0 filas en produccion.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "odontograma_lesion_apical",
        sa.Column("resuelto", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column("odontograma_lesion_apical", "resuelto", server_default=None)
    op.add_column(
        "odontograma_lesion_apical", sa.Column("resuelto_fecha", sa.Date(), nullable=True)
    )
    op.add_column(
        "odontograma_lesion_apical",
        sa.Column(
            "resuelto_por_hallazgo_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("odontograma_hallazgo.id"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("odontograma_lesion_apical", "resuelto_por_hallazgo_id")
    op.drop_column("odontograma_lesion_apical", "resuelto_fecha")
    op.drop_column("odontograma_lesion_apical", "resuelto")
