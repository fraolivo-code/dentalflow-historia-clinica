"""odontograma mixto: dientes deciduos, denticion del paciente, exfoliado, pulpotomia, pulpectomia, remision

Revision ID: 0034
Revises: 0033
Create Date: 2026-10-15

Especificacion: docs/especificaciones/historia-clinica/especificacion-tecnica-odontograma-mixto.md.
- enum denticion (adulta, mixta) y paciente.denticion (los pacientes existentes quedan «adulta»).
- 20 dientes deciduos (51-55, 61-65, 71-75, 81-85) en diente_anatomia.
- tipo_hallazgo: exfoliado, pulpotomia, pulpectomia. tipo_observacion: remision.

ALTER TYPE ... ADD VALUE va en un bloque autocommit (igual que 0025, 0027 y 0031) y los valores
nuevos no se usan en esta migracion. downgrade: Postgres no permite quitar un valor de un enum
(no-op para ellos); si se baja, se borran las columnas y los deciduos del catalogo.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0034"
down_revision: Union[str, None] = "0033"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_VALORES = ("adulta", "mixta")

# Incisivos y caninos: 1 raiz. Molares superiores: 3 (como 16/17); inferiores: 2 (como 36/37).
_SEED = (
    [(n, 1, ["Única"]) for n in (51, 52, 53, 61, 62, 63, 71, 72, 73, 81, 82, 83)]
    + [(n, 3, ["Mesiovestibular", "Palatina", "Distovestibular"]) for n in (54, 55, 64, 65)]
    + [(n, 2, ["Mesial", "Distal"]) for n in (74, 75, 84, 85)]
)


def upgrade() -> None:
    with op.get_context().autocommit_block():
        for valor in ("exfoliado", "pulpotomia", "pulpectomia"):
            op.execute(f"ALTER TYPE tipo_hallazgo ADD VALUE IF NOT EXISTS '{valor}'")
        op.execute("ALTER TYPE tipo_observacion ADD VALUE IF NOT EXISTS 'remision'")

    postgresql.ENUM(*_VALORES, name="denticion").create(op.get_bind(), checkfirst=True)
    op.add_column(
        "paciente",
        sa.Column(
            "denticion",
            postgresql.ENUM(*_VALORES, name="denticion", create_type=False),
            nullable=False,
            server_default="adulta",
        ),
    )

    tabla = sa.table(
        "diente_anatomia",
        sa.column("numero_diente", sa.SmallInteger),
        sa.column("num_raices", sa.SmallInteger),
        sa.column("nombres_raices", postgresql.ARRAY(sa.String(50))),
    )
    op.bulk_insert(
        tabla,
        [{"numero_diente": n, "num_raices": r, "nombres_raices": nombres} for n, r, nombres in _SEED],
    )


def downgrade() -> None:
    op.execute("DELETE FROM diente_anatomia WHERE numero_diente BETWEEN 51 AND 85")
    op.drop_column("paciente", "denticion")
    postgresql.ENUM(name="denticion").drop(op.get_bind(), checkfirst=True)
