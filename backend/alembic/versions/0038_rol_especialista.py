"""rol especialista: remision, atencion del especialista, registro de accesos y clave de autorizacion

Revision ID: 0038
Revises: 0037
Create Date: 2026-10-19

Diseno: docs/proceso-trabajo-caso-334.md, seccion 16.
- rol_usuario: agrega 'especialista' (ALTER TYPE ... ADD VALUE en un bloque autocommit, igual que 0025, 0027, 0031,
  0034, 0035 y 0036; el valor nuevo no se usa en esta migracion).
- usuario.pin_autorizacion_hash: la clave de autorizacion (6 digitos) de la Dra., para autorizar borrados.
- remision (+ remision_diente): la Dra. remite un paciente a un especialista; es lo que le da acceso a ESE paciente.
- atencion_especialista (+ atencion_diente): lo que el especialista hizo, firmado por el.
- acceso_paciente: quien miro que paciente (y los intentos fallidos de clave de autorizacion).
Solo tablas nuevas y una columna opcional: no se modifica ninguna fila existente.
downgrade: quita lo nuevo; el valor del enum no se puede quitar (queda sin uso).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0038"
down_revision: Union[str, None] = "0037"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _auditoria() -> list:
    return [
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("creado_por", postgresql.UUID(as_uuid=True), sa.ForeignKey("usuario.id"), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actualizado_por", postgresql.UUID(as_uuid=True), sa.ForeignKey("usuario.id"), nullable=True),
    ]


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE rol_usuario ADD VALUE IF NOT EXISTS 'especialista'")

    op.add_column("usuario", sa.Column("pin_autorizacion_hash", sa.String(255), nullable=True))

    op.create_table(
        "remision",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("paciente_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("paciente.id"), nullable=False),
        sa.Column("especialista_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("usuario.id"), nullable=False),
        sa.Column("motivo", sa.Text(), nullable=False),
        sa.Column("toda_la_boca", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("retirada_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retirada_por", postgresql.UUID(as_uuid=True), sa.ForeignKey("usuario.id"), nullable=True),
        *_auditoria(),
    )
    op.create_index("ix_remision_paciente_id", "remision", ["paciente_id"])
    op.create_index("ix_remision_especialista_id", "remision", ["especialista_id"])

    op.create_table(
        "remision_diente",
        sa.Column("remision_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("remision.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("numero_diente", sa.SmallInteger(), primary_key=True, autoincrement=False),
    )

    op.create_table(
        "atencion_especialista",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("paciente_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("paciente.id"), nullable=False),
        sa.Column("remision_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("remision.id"), nullable=False),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("procedimiento", sa.String(300), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column("indicaciones", sa.Text(), nullable=True),
        *_auditoria(),
    )
    op.create_index("ix_atencion_especialista_paciente_id", "atencion_especialista", ["paciente_id"])
    op.create_index("ix_atencion_especialista_remision_id", "atencion_especialista", ["remision_id"])

    op.create_table(
        "atencion_diente",
        sa.Column("atencion_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("atencion_especialista.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("numero_diente", sa.SmallInteger(), primary_key=True, autoincrement=False),
    )

    op.create_table(
        "acceso_paciente",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("usuario_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("usuario.id"), nullable=False),
        sa.Column("paciente_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("paciente.id"), nullable=True),
        sa.Column("momento", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accion", sa.String(60), nullable=False),
    )
    op.create_index("ix_acceso_paciente_usuario_id", "acceso_paciente", ["usuario_id"])
    op.create_index("ix_acceso_paciente_paciente_id", "acceso_paciente", ["paciente_id"])


def downgrade() -> None:
    for indice, tabla in (
        ("ix_acceso_paciente_paciente_id", "acceso_paciente"),
        ("ix_acceso_paciente_usuario_id", "acceso_paciente"),
    ):
        op.drop_index(indice, table_name=tabla)
    op.drop_table("acceso_paciente")
    op.drop_table("atencion_diente")
    op.drop_index("ix_atencion_especialista_remision_id", table_name="atencion_especialista")
    op.drop_index("ix_atencion_especialista_paciente_id", table_name="atencion_especialista")
    op.drop_table("atencion_especialista")
    op.drop_table("remision_diente")
    op.drop_index("ix_remision_especialista_id", table_name="remision")
    op.drop_index("ix_remision_paciente_id", table_name="remision")
    op.drop_table("remision")
    op.drop_column("usuario", "pin_autorizacion_hash")
