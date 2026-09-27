"""medicamento, receta y receta_medicamento (+ 4 medicamentos de ejemplo)

Revision ID: 0014
Revises: 0013
Create Date: 2026-09-26

Documento 3 de 5 de la Etapa 5 (PDF):
- medicamento: catalogo editable (mismo patron que antecedente /
  profesional_tratante, sin auditoria). Nombre unico sin distinguir
  mayusculas, para que el texto libre de una receta reuse el existente.
- receta: encabezado. emitida_por firma el PDF (sale del JWT).
- receta_medicamento: lineas (1 receta -> N), con `orden` = orden impreso.
  medicamento_nombre_impreso / presentacion_impresa: copia congelada al
  emitir (como contenido_final en indicaciones), lo que imprime el PDF.
Los medicamentos de ejemplo son solo para probar; la Dra. los revisa.
"""

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _auditoria() -> list[sa.Column]:
    return [
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("creado_por", postgresql.UUID(as_uuid=True), sa.ForeignKey("usuario.id"), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actualizado_por", postgresql.UUID(as_uuid=True), sa.ForeignKey("usuario.id"), nullable=True),
    ]


MEDICAMENTOS = [
    ("Amoxicilina", "Cápsulas de 500 mg"),
    ("Ibuprofeno", "Tabletas de 400 mg"),
    ("Acetaminofén", "Tabletas de 500 mg"),
    ("Clorhexidina 0,12 %", "Enjuague bucal"),
]


def upgrade() -> None:
    op.create_table(
        "medicamento",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("nombre", sa.String(200), nullable=False),
        sa.Column("presentacion_default", sa.String(300), nullable=True),
        sa.Column("es_favorito", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("uq_medicamento_nombre", "medicamento", [sa.text("lower(nombre)")], unique=True)

    op.create_table(
        "receta",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("paciente_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("paciente.id"), nullable=False),
        sa.Column("visita_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("visita.id"), nullable=True),
        sa.Column("tratamiento_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tratamiento.id"), nullable=True),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("notas_generales", sa.Text(), nullable=True),
        sa.Column(
            "emitida_por",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("profesional_tratante.id"),
            nullable=False,
        ),
        *_auditoria(),
    )
    op.create_index("ix_receta_paciente_id", "receta", ["paciente_id"])

    op.create_table(
        "receta_medicamento",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "receta_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("receta.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("orden", sa.SmallInteger(), nullable=False),
        sa.Column("medicamento_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("medicamento.id"), nullable=False),
        sa.Column("medicamento_nombre_impreso", sa.String(200), nullable=False),
        sa.Column("presentacion_impresa", sa.String(300), nullable=True),
        sa.Column("dosis", sa.String(200), nullable=False),
        sa.Column("via", sa.String(100), nullable=True),
        sa.Column("frecuencia", sa.String(200), nullable=False),
        sa.Column("duracion", sa.String(200), nullable=False),
        sa.Column("indicaciones_adicionales", sa.Text(), nullable=True),
    )
    op.create_index("ix_receta_medicamento_receta_id", "receta_medicamento", ["receta_id"])

    conexion = op.get_bind()
    for nombre, presentacion in MEDICAMENTOS:
        conexion.execute(
            sa.text(
                "INSERT INTO medicamento (id, nombre, presentacion_default, es_favorito) "
                "VALUES (:id, :nombre, :presentacion, true)"
            ),
            {"id": uuid.uuid4(), "nombre": nombre, "presentacion": presentacion},
        )


def downgrade() -> None:
    op.drop_table("receta_medicamento")
    op.drop_table("receta")
    op.drop_table("medicamento")
