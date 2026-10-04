"""bitacora_diente: varios dientes por entrada de bitacora

Revision ID: 0022
Revises: 0021
Create Date: 2026-10-04

Una fila por diente de cada entrada. La columna bitacora_tratamiento.numero_diente
se CONSERVA (compatibilidad) y guarda el primer diente de la entrada.

Entradas existentes: cada entrada con numero_diente se copia a bitacora_diente
(un diente), conservando su creado_en/creado_por. No se modifica ni se borra
ninguna entrada. Las que no tienen diente no generan filas.

Reversible: el downgrade borra bitacora_diente. Como la columna numero_diente
sigue ahi con el primer diente, solo se pierden los dientes ADICIONALES de las
entradas creadas con varios dientes.
"""

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0022"
down_revision: Union[str, None] = "0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    tabla = op.create_table(
        "bitacora_diente",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "bitacora_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("bitacora_tratamiento.id"),
            nullable=False,
        ),
        sa.Column(
            "numero_diente",
            sa.SmallInteger(),
            sa.ForeignKey("diente_anatomia.numero_diente"),
            nullable=False,
        ),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "creado_por", postgresql.UUID(as_uuid=True), sa.ForeignKey("usuario.id"), nullable=False
        ),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "actualizado_por",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("usuario.id"),
            nullable=True,
        ),
        sa.UniqueConstraint("bitacora_id", "numero_diente", name="uq_bitacora_diente"),
    )
    op.create_index("ix_bitacora_diente_bitacora_id", "bitacora_diente", ["bitacora_id"])
    op.create_index("ix_bitacora_diente_numero_diente", "bitacora_diente", ["numero_diente"])

    # Entradas existentes: su unico diente pasa a la tabla nueva. Se lee con
    # columnas tipadas (UUID/fechas ya convertidos por SQLAlchemy) para que
    # funcione igual en Postgres y en SQLite.
    bitacora = sa.table(
        "bitacora_tratamiento",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("numero_diente", sa.SmallInteger),
        sa.column("creado_en", sa.DateTime(timezone=True)),
        sa.column("creado_por", postgresql.UUID(as_uuid=True)),
    )
    entradas = (
        op.get_bind()
        .execute(sa.select(bitacora).where(bitacora.c.numero_diente.is_not(None)))
        .fetchall()
    )
    if entradas:
        op.bulk_insert(
            tabla,
            [
                {
                    "id": uuid.uuid4(),
                    "bitacora_id": e.id,
                    "numero_diente": e.numero_diente,
                    "creado_en": e.creado_en,
                    "creado_por": e.creado_por,
                }
                for e in entradas
            ],
        )


def downgrade() -> None:
    op.drop_index("ix_bitacora_diente_numero_diente", table_name="bitacora_diente")
    op.drop_index("ix_bitacora_diente_bitacora_id", table_name="bitacora_diente")
    op.drop_table("bitacora_diente")
