"""membrete del profesional (direccion, telefonos, correo, RIF, COV, MPPS) y direccion corta del paciente

Revision ID: 0039
Revises: 0038
Create Date: 2026-10-20

Los recipes reales llevan direccion, telefonos, correo, RIF, COV y MPPS del profesional, y el paciente con su cedula,
fecha de nacimiento y una direccion corta (municipio). Solo se agregan columnas opcionales: no se borra ni se cambia
ningun dato existente. Unico paso sobre datos: si el texto antiguo `numero_colegiatura` tiene exactamente la forma
«C.O.V. 15766 - M.S.D.S. 15491», se copian esos dos numeros a `cov` y `mpps` (el texto antiguo se conserva).
downgrade: quita las columnas nuevas.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0039"
down_revision: Union[str, None] = "0038"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("profesional_tratante", sa.Column("direccion", sa.Text(), nullable=True))
    op.add_column("profesional_tratante", sa.Column("telefonos", sa.String(300), nullable=True))
    op.add_column("profesional_tratante", sa.Column("correo", sa.String(254), nullable=True))
    op.add_column("profesional_tratante", sa.Column("rif", sa.String(30), nullable=True))
    op.add_column("profesional_tratante", sa.Column("cov", sa.String(50), nullable=True))
    op.add_column("profesional_tratante", sa.Column("mpps", sa.String(50), nullable=True))
    op.add_column("paciente", sa.Column("direccion_corta", sa.String(120), nullable=True))
    op.execute(
        r"""
        UPDATE profesional_tratante
        SET cov = substring(numero_colegiatura from 'C\.O\.V\. ([0-9]+)'),
            mpps = substring(numero_colegiatura from 'M\.S\.D\.S\. ([0-9]+)')
        WHERE numero_colegiatura ~ '^C\.O\.V\. [0-9]+ - M\.S\.D\.S\. [0-9]+$'
        """
    )


def downgrade() -> None:
    op.drop_column("paciente", "direccion_corta")
    for columna in ("mpps", "cov", "rif", "correo", "telefonos", "direccion"):
        op.drop_column("profesional_tratante", columna)
