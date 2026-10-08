"""paciente.cedula unica (solo entre las que tienen valor)

Revision ID: 0028
Revises: 0027
Create Date: 2026-10-07

Evita fichas duplicadas: la cedula (V-12345678) no puede repetirse. Indice
parcial: los pacientes sin cedula (menores de 12, historias antiguas) no chocan.
Falla si ya hay cedulas repetidas; revisar los datos antes de aplicarla.
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0028"
down_revision: Union[str, None] = "0027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "uq_paciente_cedula",
        "paciente",
        ["cedula"],
        unique=True,
        postgresql_where="cedula IS NOT NULL",
        sqlite_where="cedula IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_index("uq_paciente_cedula", table_name="paciente")
