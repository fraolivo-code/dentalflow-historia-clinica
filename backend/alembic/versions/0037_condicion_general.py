"""odontograma: condiciones de toda la boca (gingivitis general); se retira paciente.seguimiento_periodontal_texto

Revision ID: 0037
Revises: 0036
Create Date: 2026-10-19

Decision de la Dra. (docs/proceso-trabajo-caso-334.md, sec. 15):
- La gingivitis no es de un diente: se marca una vez para toda la boca y se dibuja «GING» al centro del
  odontograma. Tabla nueva `odontograma_condicion_general` (con su enum). Los hallazgos «gingivitis» por diente
  que existieran se convierten en UNA condicion general por paciente (fecha = la mas antigua) y quedan resueltos;
  no se borra nada.
- Periodontitis: ademas de la de un diente (hallazgo «requiere_periodontal»), hay una periodontitis general o de varios
  dientes (condicion general, boton del odontograma).
- `paciente.seguimiento_periodontal_texto` se retira: el diagnostico periodontal va solo en la nota de la visita.
  Esa columna nunca se pidio en pantalla a los pacientes reales; si tuviera algun valor, queda en el backup
  que se hace antes de publicar.

El valor 'gingivitis' del enum tipo_hallazgo (0036) queda sin uso nuevo; Postgres no permite quitar valores.
downgrade: vuelve la columna (vacia) y quita la tabla; la conversion de gingivitis no se revierte.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0037"
down_revision: Union[str, None] = "0036"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_VALORES = ("gingivitis", "periodontitis")


def upgrade() -> None:
    postgresql.ENUM(*_VALORES, name="condicion_general").create(op.get_bind(), checkfirst=True)
    op.create_table(
        "odontograma_condicion_general",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("paciente_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("paciente.id"), nullable=False),
        sa.Column("visita_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("visita.id"), nullable=True),
        sa.Column("tipo", postgresql.ENUM(*_VALORES, name="condicion_general", create_type=False), nullable=False),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("resuelto", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("resuelto_fecha", sa.Date(), nullable=True),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("creado_por", postgresql.UUID(as_uuid=True), sa.ForeignKey("usuario.id"), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actualizado_por", postgresql.UUID(as_uuid=True), sa.ForeignKey("usuario.id"), nullable=True),
    )
    op.create_index("ix_odontograma_condicion_general_paciente_id", "odontograma_condicion_general", ["paciente_id"])

    # Gingivitis por diente (0036) -> una condicion general por paciente; los hallazgos quedan resueltos.
    op.execute(
        """
        INSERT INTO odontograma_condicion_general (id, paciente_id, tipo, fecha, resuelto, creado_en, creado_por)
        SELECT gen_random_uuid(), paciente_id, 'gingivitis'::condicion_general, MIN(fecha), false, now(),
               (array_agg(creado_por ORDER BY fecha))[1]
        FROM odontograma_hallazgo
        WHERE tipo_hallazgo = 'gingivitis' AND resuelto = false
        GROUP BY paciente_id
        """
    )
    op.execute(
        """
        UPDATE odontograma_hallazgo
        SET resuelto = true, resuelto_fecha = CURRENT_DATE
        WHERE tipo_hallazgo = 'gingivitis' AND resuelto = false
        """
    )

    op.drop_column("paciente", "seguimiento_periodontal_texto")


def downgrade() -> None:
    op.add_column("paciente", sa.Column("seguimiento_periodontal_texto", sa.Text(), nullable=True))
    op.drop_index("ix_odontograma_condicion_general_paciente_id", table_name="odontograma_condicion_general")
    op.drop_table("odontograma_condicion_general")
    postgresql.ENUM(name="condicion_general").drop(op.get_bind(), checkfirst=True)
