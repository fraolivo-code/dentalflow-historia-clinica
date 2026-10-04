"""numeracion configurable de historias y seguro del paciente

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-04

- configuracion_consultorio.numero_ancho: cantidad de digitos (con ceros a la
  izquierda) del numero de historia. Por defecto 4, igual al formato actual.
- paciente.seguro: texto libre y opcional (sin lista de aseguradoras).

No toca la secuencia paciente_numero_historia_seq: el punto de partida se fija
desde la aplicacion (PUT /configuracion/numeracion).

Reversible: el downgrade quita ambas columnas (y los datos que contengan).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0020"
down_revision: Union[str, None] = "0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "configuracion_consultorio",
        sa.Column("numero_ancho", sa.Integer(), nullable=False, server_default="4"),
    )
    op.add_column("paciente", sa.Column("seguro", sa.String(120), nullable=True))


def downgrade() -> None:
    op.drop_column("paciente", "seguro")
    op.drop_column("configuracion_consultorio", "numero_ancho")
