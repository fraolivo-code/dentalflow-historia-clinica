"""gestion de usuarios y contrasenas: columnas nuevas en usuario, token_recuperacion y auditoria_usuario

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-03

usuario: email (unico entre los no nulos), debe_cambiar_clave (false para los
actuales), clave_cambiada_en, intentos_fallidos, bloqueado_hasta, ultimo_login,
creado_por, actualizado_en. Nombres sin distinguir mayusculas: si dos nombres
existentes solo difieren en mayusculas la migracion SE DETIENE (no los
fusiona); si no, pasa los nombres a minusculas y sin espacios en los bordes.

Tablas nuevas: token_recuperacion (solo el SHA-256 del token) y
auditoria_usuario. Se usa batch_alter_table para que la misma migracion corra
en Postgres (ALTER directo) y en SQLite (tests).

Reversible en estructura. Lo unico que el downgrade no puede recuperar es la
capitalizacion original de los nombres (quedan en minusculas).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0018"
down_revision: Union[str, None] = "0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _normalizar_nombres() -> None:
    conexion = op.get_bind()
    filas = conexion.execute(sa.text("SELECT id, nombre FROM usuario")).all()
    por_normalizado: dict[str, list[str]] = {}
    for _, nombre in filas:
        por_normalizado.setdefault(nombre.strip().lower(), []).append(nombre)
    repetidos = {k: v for k, v in por_normalizado.items() if len(v) > 1}
    if repetidos:
        detalle = "; ".join(" / ".join(repr(n) for n in nombres) for nombres in repetidos.values())
        raise RuntimeError(
            "Migracion 0018 detenida: hay nombres de usuario que solo difieren en "
            f"mayusculas o espacios ({detalle}). Renombre o elimine los duplicados "
            "a mano y vuelva a desplegar. No se modifico nada."
        )
    for id_, nombre in filas:
        normalizado = nombre.strip().lower()
        if normalizado != nombre:
            conexion.execute(
                sa.text("UPDATE usuario SET nombre = :nombre WHERE id = :id"),
                {"nombre": normalizado, "id": id_},
            )


def upgrade() -> None:
    _normalizar_nombres()

    with op.batch_alter_table("usuario") as batch:
        batch.add_column(sa.Column("email", sa.String(254), nullable=True))
        batch.add_column(
            sa.Column(
                "debe_cambiar_clave", sa.Boolean(), nullable=False, server_default=sa.false()
            )
        )
        batch.add_column(sa.Column("clave_cambiada_en", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(
            sa.Column("intentos_fallidos", sa.Integer(), nullable=False, server_default="0")
        )
        batch.add_column(sa.Column("bloqueado_hasta", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("ultimo_login", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("creado_por", postgresql.UUID(as_uuid=True), nullable=True))
        batch.add_column(sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=True))
        # Con nombre: batch (SQLite) lo exige y el downgrade lo quita por nombre.
        batch.create_foreign_key("fk_usuario_creado_por", "usuario", ["creado_por"], ["id"])
    # Indice unico: los NULL no chocan entre si (Postgres y SQLite).
    op.create_index("uq_usuario_email", "usuario", ["email"], unique=True)

    op.create_table(
        "token_recuperacion",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "usuario_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("usuario.id"), nullable=False
        ),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expira_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("usado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_token_recuperacion_usuario_id", "token_recuperacion", ["usuario_id"])

    op.create_table(
        "auditoria_usuario",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("fecha", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "actor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("usuario.id"), nullable=True
        ),
        sa.Column("accion", sa.String(40), nullable=False),
        sa.Column(
            "usuario_objetivo_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("usuario.id"),
            nullable=True,
        ),
        sa.Column("detalle", sa.String(200), nullable=True),
    )
    op.create_index("ix_auditoria_usuario_fecha", "auditoria_usuario", ["fecha"])


def downgrade() -> None:
    op.drop_index("ix_auditoria_usuario_fecha", table_name="auditoria_usuario")
    op.drop_table("auditoria_usuario")
    op.drop_index("ix_token_recuperacion_usuario_id", table_name="token_recuperacion")
    op.drop_table("token_recuperacion")

    op.drop_index("uq_usuario_email", table_name="usuario")
    with op.batch_alter_table("usuario") as batch:
        batch.drop_constraint("fk_usuario_creado_por", type_="foreignkey")
        for columna in (
            "actualizado_en",
            "creado_por",
            "ultimo_login",
            "bloqueado_hasta",
            "intentos_fallidos",
            "clave_cambiada_en",
            "debe_cambiar_clave",
            "email",
        ):
            batch.drop_column(columna)
