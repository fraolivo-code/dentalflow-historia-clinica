"""etapa 3: autenticacion — password_hash y nombre unico en usuario

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-19

`nombre` pasa a ser tambien el identificador de login (el modelo `usuario`
no tiene un campo de username/email separado), por eso necesita ser unico.
La tabla esta vacia en todos los entornos conocidos, asi que password_hash
puede agregarse NOT NULL directamente sin backfill.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "usuario", sa.Column("password_hash", sa.String(length=255), nullable=False)
    )
    op.create_unique_constraint("uq_usuario_nombre", "usuario", ["nombre"])


def downgrade() -> None:
    op.drop_constraint("uq_usuario_nombre", "usuario", type_="unique")
    op.drop_column("usuario", "password_hash")
