"""visita.tipo (tipo de visita) y visita_tratamiento

Revision ID: 0030
Revises: 0029
Create Date: 2026-10-14

Flujo de visitas (especificacion-tecnica-flujo-visitas-tratamientos.md, fase 1):
la visita pasa a tener un tipo (evaluacion, tratamiento, control_limpieza,
emergencia, otra) que decide que pide la pantalla, y se vincula con los
tratamientos a los que corresponde. Columna nullable y tabla nueva: no toca filas.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0030"
down_revision: Union[str, None] = "0029"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_VALORES = ("evaluacion", "tratamiento", "control_limpieza", "emergencia", "otra")


def upgrade() -> None:
    postgresql.ENUM(*_VALORES, name="tipo_visita").create(op.get_bind(), checkfirst=True)
    op.add_column(
        "visita",
        sa.Column("tipo", postgresql.ENUM(*_VALORES, name="tipo_visita", create_type=False), nullable=True),
    )
    op.create_table(
        "visita_tratamiento",
        sa.Column("visita_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("visita.id"), primary_key=True),
        sa.Column(
            "tratamiento_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tratamiento.id"), primary_key=True
        ),
    )
    op.create_index("ix_visita_tratamiento_tratamiento_id", "visita_tratamiento", ["tratamiento_id"])


def downgrade() -> None:
    op.drop_index("ix_visita_tratamiento_tratamiento_id", table_name="visita_tratamiento")
    op.drop_table("visita_tratamiento")
    op.drop_column("visita", "tipo")
    postgresql.ENUM(name="tipo_visita").drop(op.get_bind(), checkfirst=True)
