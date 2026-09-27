"""consentimiento.tratamiento_id (consentimiento por tratamiento)

Revision ID: 0015
Revises: 0014
Create Date: 2026-09-26

Especificacion de formularios, seccion 8: el consentimiento de tratamiento
vive al pie de cada `tratamiento` y se renueva con cada tratamiento nuevo.
Hasta ahora `consentimiento` solo colgaba del paciente. Nullable: el de
almacenamiento digital no pertenece a ningun tratamiento. Solo el modelo; el
flujo que exige un consentimiento nuevo por tratamiento queda para despues.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "consentimiento",
        sa.Column(
            "tratamiento_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tratamiento.id"),
            nullable=True,
        ),
    )
    op.create_index("ix_consentimiento_tratamiento_id", "consentimiento", ["tratamiento_id"])


def downgrade() -> None:
    op.drop_index("ix_consentimiento_tratamiento_id", table_name="consentimiento")
    op.drop_column("consentimiento", "tratamiento_id")
