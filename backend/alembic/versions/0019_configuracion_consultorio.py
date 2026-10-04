"""configuracion_consultorio: portada configurable (nombre, frase e imagen)

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-03

Tabla de UNA sola fila (id fijo = 1), creada vacia por esta migracion. La
imagen vive en la base (entra en el backup semanal) y la API la guarda ya
re-codificada y de maximo 1 MB. Sin configuracion se usa NOMBRE_PRODUCTO.

Reversible: el downgrade borra la tabla (y con ella la imagen y los textos).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0019"
down_revision: Union[str, None] = "0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "configuracion_consultorio",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("nombre", sa.String(120), nullable=True),
        sa.Column("frase", sa.String(200), nullable=True),
        sa.Column("imagen", sa.LargeBinary(), nullable=True),
        sa.Column("imagen_tipo", sa.String(20), nullable=True),
        sa.Column("imagen_actualizada_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "actualizado_por",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("usuario.id"),
            nullable=True,
        ),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(sa.text("INSERT INTO configuracion_consultorio (id) VALUES (1)"))


def downgrade() -> None:
    op.drop_table("configuracion_consultorio")
