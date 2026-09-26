"""plantilla_indicacion e indicacion_tratamiento (+ 2 plantillas de ejemplo)

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-26

Documento 2 de 5 de la Etapa 5 (PDF):
- plantilla_indicacion: catalogo editable por la Dra. (nombre,
  tipo_tratamiento en texto libre, contenido). Sin borrado.
- indicacion_tratamiento: lo entregado al paciente. contenido_final es una
  copia independiente de la plantilla, para que editar la plantilla despues
  no altere lo ya entregado. emitida_por firma el PDF (sale del JWT).
Las plantillas de ejemplo se siembran a nombre de la cuenta dra; si no hay
ninguna (base nueva), no se siembra nada.
"""

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _auditoria() -> list[sa.Column]:
    return [
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("creado_por", postgresql.UUID(as_uuid=True), sa.ForeignKey("usuario.id"), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actualizado_por", postgresql.UUID(as_uuid=True), sa.ForeignKey("usuario.id"), nullable=True),
    ]


POST_EXTRACCION = """Mantenga la gasa mordiendo con presión firme durante 30 a 45 minutos. Si al retirarla sigue sangrando, coloque una gasa limpia doblada sobre la zona y vuelva a morder otros 30 minutos.

Durante las primeras 24 horas:
- No se enjuague, no escupa ni haga buches: el coágulo que se forma en la zona es necesario para que cicatrice.
- No use pitillo para beber.
- No fume ni tome bebidas alcohólicas (lo ideal es no fumar durante al menos 72 horas).
- Aplique frío por fuera de la cara, sobre la zona (hielo envuelto en un paño), 15 minutos sí y 15 minutos no, durante las primeras 6 horas.
- Evite el esfuerzo físico intenso y duerma con la cabeza un poco elevada.

Alimentación: dieta blanda, fría o tibia (nunca caliente) durante el primer día: yogur, helado, compotas, purés, sopas tibias. Mastique del lado contrario a la extracción.

Higiene: cepille el resto de los dientes con normalidad desde esta misma noche, con cuidado en la zona de la extracción. A partir del día siguiente, haga enjuagues suaves con agua tibia y sal (media cucharadita en un vaso de agua) después de cada comida, sin buches fuertes.

Medicación: tome solo lo indicado por la doctora, en las dosis y horarios indicados. No tome aspirina salvo indicación médica: favorece el sangrado.

Es normal una inflamación leve durante los primeros 2 a 3 días, una molestia moderada que cede con la medicación y saliva teñida de rosado durante el primer día.

Comuníquese con el consultorio si presenta sangrado abundante que no cede con la gasa, dolor intenso que aumenta a partir del tercer día, fiebre o inflamación que sigue aumentando después de 72 horas."""

POST_ENDODONCIA = """Es normal sentir sensibilidad o molestia al morder durante los primeros días (de 2 a 5 días). Tome el analgésico indicado, en las dosis y horarios que le dio la doctora.

Mientras tenga la obturación provisional:
- No coma durante las 2 horas siguientes a la consulta, hasta que el material endurezca.
- Evite masticar del lado tratado alimentos duros o pegajosos (caramelos, chicles, turrones).
- Es normal que el provisional se desgaste un poco; si se cae por completo, comuníquese con el consultorio.

Un diente con tratamiento de conducto queda más frágil y puede fracturarse. Es importante colocar la restauración definitiva (resina, incrustación o corona) en el plazo indicado por la doctora.

Mantenga su higiene habitual: cepillado y uso de hilo dental con normalidad, también en el diente tratado.

Comuníquese con el consultorio si presenta dolor intenso que no cede con la medicación, inflamación de la cara o de la encía, fiebre, o si siente que al morder el diente tratado toca antes que los demás."""

PLANTILLAS = [
    ("Post-extracción simple", "extracción", POST_EXTRACCION),
    ("Post-endodoncia", "endodoncia", POST_ENDODONCIA),
]


def upgrade() -> None:
    op.create_table(
        "plantilla_indicacion",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("nombre", sa.String(200), nullable=False, unique=True),
        sa.Column("tipo_tratamiento", sa.String(200), nullable=True),
        sa.Column("contenido", sa.Text(), nullable=False),
        *_auditoria(),
    )

    op.create_table(
        "indicacion_tratamiento",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("paciente_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("paciente.id"), nullable=False),
        sa.Column("visita_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("visita.id"), nullable=True),
        sa.Column("tratamiento_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tratamiento.id"), nullable=True),
        sa.Column(
            "plantilla_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("plantilla_indicacion.id"),
            nullable=True,
        ),
        sa.Column("contenido_final", sa.Text(), nullable=False),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column(
            "emitida_por",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("profesional_tratante.id"),
            nullable=False,
        ),
        *_auditoria(),
    )
    op.create_index(
        "ix_indicacion_tratamiento_paciente_id", "indicacion_tratamiento", ["paciente_id"]
    )

    conexion = op.get_bind()
    dra = conexion.execute(
        sa.text("SELECT id FROM usuario WHERE rol = 'dra' ORDER BY creado_en LIMIT 1")
    ).scalar()
    if dra is None:
        return
    for nombre, tipo, contenido in PLANTILLAS:
        conexion.execute(
            sa.text(
                "INSERT INTO plantilla_indicacion (id, nombre, tipo_tratamiento, contenido, creado_en, creado_por) "
                "VALUES (:id, :nombre, :tipo, :contenido, now(), :dra)"
            ),
            {"id": uuid.uuid4(), "nombre": nombre, "tipo": tipo, "contenido": contenido, "dra": dra},
        )


def downgrade() -> None:
    op.drop_table("indicacion_tratamiento")
    op.drop_table("plantilla_indicacion")
