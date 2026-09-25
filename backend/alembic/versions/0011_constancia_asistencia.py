"""constancia_asistencia; profesional_tratante: numero_colegiatura y usuario_id

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-25

Documento 1 de 5 de la Etapa 5 (PDF), especificado el 19/09/2026:
- constancia_asistencia: solo confirma asistencia (uso laboral del paciente),
  SIN motivo ni diagnostico. hora_inicio/hora_fin se cargan al emitir, no
  dependen de que la visita tenga hora.
- profesional_tratante.numero_colegiatura: especificado para la receta y la
  constancia, nunca se habia agregado. Nullable hasta tener el dato real.
- profesional_tratante.usuario_id (25/09/2026): vincula la cuenta de acceso
  con el profesional que firma, para derivar emitida_por del JWT en vez de
  aceptarlo del cliente. Unico: una cuenta firma como un solo profesional.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "profesional_tratante",
        sa.Column("numero_colegiatura", sa.String(100), nullable=True),
    )
    op.add_column(
        "profesional_tratante",
        sa.Column(
            "usuario_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("usuario.id"),
            nullable=True,
        ),
    )
    op.create_unique_constraint(
        "uq_profesional_tratante_usuario_id", "profesional_tratante", ["usuario_id"]
    )

    op.create_table(
        "constancia_asistencia",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("paciente_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("paciente.id"), nullable=False),
        sa.Column("visita_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("visita.id"), nullable=False),
        sa.Column("fecha_emision", sa.Date(), nullable=False),
        sa.Column("hora_inicio", sa.Time(), nullable=True),
        sa.Column("hora_fin", sa.Time(), nullable=True),
        sa.Column("texto_adicional", sa.Text(), nullable=True),
        sa.Column(
            "emitida_por",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("profesional_tratante.id"),
            nullable=False,
        ),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("creado_por", postgresql.UUID(as_uuid=True), sa.ForeignKey("usuario.id"), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actualizado_por", postgresql.UUID(as_uuid=True), sa.ForeignKey("usuario.id"), nullable=True),
        sa.CheckConstraint(
            "hora_inicio IS NULL OR hora_fin IS NULL OR hora_fin > hora_inicio",
            name="ck_constancia_asistencia_horario",
        ),
    )
    op.create_index(
        "ix_constancia_asistencia_paciente_id", "constancia_asistencia", ["paciente_id"]
    )


def downgrade() -> None:
    op.drop_table("constancia_asistencia")
    op.drop_constraint(
        "uq_profesional_tratante_usuario_id", "profesional_tratante", type_="unique"
    )
    op.drop_column("profesional_tratante", "usuario_id")
    op.drop_column("profesional_tratante", "numero_colegiatura")
