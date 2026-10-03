"""paciente.movil_normalizado (vinculacion Alma, Etapa 6)

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-02

Columna nullable + indice, y recalculo para los pacientes existentes con la
MISMA funcion Python que usa el modelo (app/services/movil.py), sin funciones
especificas de Postgres. `movil` no se toca. No unica: un mismo numero puede
pertenecer a varios pacientes (familiares).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.services.movil import normalizar_movil

# revision identifiers, used by Alembic.
revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("paciente", sa.Column("movil_normalizado", sa.String(15), nullable=True))
    op.create_index("ix_paciente_movil_normalizado", "paciente", ["movil_normalizado"])

    paciente = sa.table(
        "paciente",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("movil", sa.String),
        sa.column("movil_normalizado", sa.String),
    )
    conexion = op.get_bind()
    for fila in conexion.execute(sa.select(paciente.c.id, paciente.c.movil)).all():
        normalizado = normalizar_movil(fila.movil)
        if normalizado is not None:
            conexion.execute(
                sa.update(paciente)
                .where(paciente.c.id == fila.id)
                .values(movil_normalizado=normalizado)
            )


def downgrade() -> None:
    op.drop_index("ix_paciente_movil_normalizado", table_name="paciente")
    op.drop_column("paciente", "movil_normalizado")
