"""Etapa 3 (formularios de captura): paciente, antecedente, tratamiento,
bitacora, observacion, odontograma_hallazgo.resuelto

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-14

Implementa especificacion-tecnica-formularios-fase2.md. Puntos de esquema
que no vienen con una tabla de campos en ningun documento (antecedente,
paciente_antecedente, bitacora_tratamiento, observacion) se reconstruyeron a
partir de proceso-automatizacion-odontologo-v2.md y se confirmaron con la
Dra./desarrollador antes de esta migracion (ver conversacion de la sesion).

Nota sobre datos: paciente estaba en 0 filas al momento de escribir esta
migracion (limpiada al cierre de la sesion de validacion anterior), por lo
que las columnas NOT NULL nuevas (paciente.numero_historia,
odontograma_hallazgo.resuelto/origen) no requieren backfill.
"""

from typing import Sequence, Union
import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


origen_hallazgo = postgresql.ENUM("aqui", "externo", name="origen_hallazgo", create_type=False)
estado_tratamiento = postgresql.ENUM(
    "indicado", "en_curso", "completado", "suspendido", name="estado_tratamiento", create_type=False
)
origen_tratamiento = postgresql.ENUM(
    "aqui", "remitido_externo", name="origen_tratamiento", create_type=False
)
tipo_observacion = postgresql.ENUM(
    "clinica", "administrativa", "otra", name="tipo_observacion", create_type=False
)

NEW_ENUMS = [origen_hallazgo, estado_tratamiento, origen_tratamiento, tipo_observacion]

# Catalogo de antecedente (seccion 2). UUIDs fijos generados una vez al
# escribir esta migracion, para que el seed sea reproducible.
ANTECEDENTE_SEED = [
    {"id": uuid.UUID("7df36599-e31e-4d82-91b1-4a27e40cacdc"), "nombre": "Diabetes", "requiere_detalle": False},
    {"id": uuid.UUID("d70c3440-10ba-4614-865d-b93b1f3cb195"), "nombre": "Hepatitis", "requiere_detalle": True},
    {"id": uuid.UUID("40946524-c0b6-48e6-baee-ac5e3f644b18"), "nombre": "E. Cardíaca", "requiere_detalle": False},
    {"id": uuid.UUID("78c296f7-4137-4993-a2f7-3e0b9c225054"), "nombre": "Tensión", "requiere_detalle": False},
    {"id": uuid.UUID("85d15546-33de-4529-abde-d214e22af86a"), "nombre": "Herpes", "requiere_detalle": False},
    {"id": uuid.UUID("b9ddd5a2-a255-42e2-8a04-178f2050b201"), "nombre": "Alergias", "requiere_detalle": False},
    {"id": uuid.UUID("c1b1c3c6-215f-494b-85e2-5c4d67830f37"), "nombre": "Traumatismos faciales", "requiere_detalle": False},
    {"id": uuid.UUID("822fcf38-ef70-493a-a778-0430d2da4e3c"), "nombre": "Convulsiones", "requiere_detalle": True},
    {"id": uuid.UUID("47089fa3-c8a7-48f3-ae63-2533ea025815"), "nombre": "Operaciones", "requiere_detalle": True},
    {"id": uuid.UUID("91543823-9921-47c3-b896-c924dec8fbab"), "nombre": "Otras", "requiere_detalle": False},
]

PROFESIONAL_TRATANTE_SEED = [
    {
        "id": uuid.UUID("ec86b49f-cba2-4d78-b402-34fd08e49659"),
        "nombre": "Leonor Granados",
        "especialidad": None,
    },
]


def upgrade() -> None:
    bind = op.get_bind()
    for enum_type in NEW_ENUMS:
        enum_type.create(bind, checkfirst=True)

    # --- 1. paciente ---------------------------------------------------
    op.add_column("paciente", sa.Column("numero_historia", sa.String(50), nullable=False))
    op.create_unique_constraint("uq_paciente_numero_historia", "paciente", ["numero_historia"])
    op.add_column("paciente", sa.Column("fecha_primera_consulta_real", sa.Date(), nullable=True))
    op.add_column("paciente", sa.Column("historia_origen", sa.Text(), nullable=True))
    op.add_column("paciente", sa.Column("documento_historia_anterior", sa.String(1000), nullable=True))
    op.add_column("paciente", sa.Column("foto", sa.String(1000), nullable=True))

    # --- 2. antecedente + paciente_antecedente --------------------------
    op.create_table(
        "antecedente",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("nombre", sa.String(200), nullable=False),
        sa.Column("requiere_detalle", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("nombre", name="uq_antecedente_nombre"),
    )

    op.create_table(
        "paciente_antecedente",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("paciente_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("paciente.id"), nullable=False),
        sa.Column("antecedente_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("antecedente.id"), nullable=False),
        sa.Column("presente", sa.Boolean(), nullable=False),
        sa.Column("detalle", sa.Text(), nullable=True),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("creado_por", postgresql.UUID(as_uuid=True), sa.ForeignKey("usuario.id"), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actualizado_por", postgresql.UUID(as_uuid=True), sa.ForeignKey("usuario.id"), nullable=True),
        sa.UniqueConstraint("paciente_id", "antecedente_id", name="uq_paciente_antecedente"),
    )
    op.create_index("ix_paciente_antecedente_paciente_id", "paciente_antecedente", ["paciente_id"])
    op.create_index("ix_paciente_antecedente_antecedente_id", "paciente_antecedente", ["antecedente_id"])

    antecedente_table = sa.table(
        "antecedente",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("nombre", sa.String(200)),
        sa.column("requiere_detalle", sa.Boolean()),
    )
    op.bulk_insert(antecedente_table, ANTECEDENTE_SEED)

    # --- 3. visita: examen_tomografia ----------------------------------
    op.add_column(
        "visita",
        sa.Column("examen_tomografia", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column("visita", "examen_tomografia", server_default=None)

    # --- 4. profesional_tratante -----------------------------------------
    op.create_table(
        "profesional_tratante",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("nombre", sa.String(300), nullable=False),
        sa.Column("especialidad", sa.String(300), nullable=True),
    )
    profesional_tratante_table = sa.table(
        "profesional_tratante",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("nombre", sa.String(300)),
        sa.column("especialidad", sa.String(300)),
    )
    op.bulk_insert(profesional_tratante_table, PROFESIONAL_TRATANTE_SEED)

    # --- 5. tratamiento + tratamiento_diente -----------------------------
    op.create_table(
        "tratamiento",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("paciente_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("paciente.id"), nullable=False),
        sa.Column("tipo", sa.String(200), nullable=False),
        sa.Column("estado", estado_tratamiento, nullable=False),
        sa.Column("origen", origen_tratamiento, nullable=False),
        sa.Column("origen_detalle", sa.Text(), nullable=True),
        sa.Column("fecha_inicio", sa.Date(), nullable=False),
        sa.Column("fecha_fin", sa.Date(), nullable=True),
        sa.Column(
            "profesional_tratante_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("profesional_tratante.id"),
            nullable=False,
        ),
        sa.Column("notas_relevantes", sa.Text(), nullable=True),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("creado_por", postgresql.UUID(as_uuid=True), sa.ForeignKey("usuario.id"), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actualizado_por", postgresql.UUID(as_uuid=True), sa.ForeignKey("usuario.id"), nullable=True),
    )
    op.create_index("ix_tratamiento_paciente_id", "tratamiento", ["paciente_id"])

    op.create_table(
        "tratamiento_diente",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tratamiento_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tratamiento.id"), nullable=False),
        sa.Column(
            "numero_diente",
            sa.SmallInteger(),
            sa.ForeignKey("diente_anatomia.numero_diente"),
            nullable=False,
        ),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("creado_por", postgresql.UUID(as_uuid=True), sa.ForeignKey("usuario.id"), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actualizado_por", postgresql.UUID(as_uuid=True), sa.ForeignKey("usuario.id"), nullable=True),
    )
    op.create_index("ix_tratamiento_diente_tratamiento_id", "tratamiento_diente", ["tratamiento_id"])
    op.create_index("ix_tratamiento_diente_numero_diente", "tratamiento_diente", ["numero_diente"])

    # --- 6. bitacora_tratamiento ------------------------------------------
    op.create_table(
        "bitacora_tratamiento",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("paciente_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("paciente.id"), nullable=False),
        sa.Column("visita_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("visita.id"), nullable=True),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("responsable", postgresql.UUID(as_uuid=True), sa.ForeignKey("usuario.id"), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=False),
        sa.Column(
            "numero_diente",
            sa.SmallInteger(),
            sa.ForeignKey("diente_anatomia.numero_diente"),
            nullable=True,
        ),
        sa.Column("tratamiento_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tratamiento.id"), nullable=True),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("creado_por", postgresql.UUID(as_uuid=True), sa.ForeignKey("usuario.id"), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actualizado_por", postgresql.UUID(as_uuid=True), sa.ForeignKey("usuario.id"), nullable=True),
    )
    op.create_index("ix_bitacora_tratamiento_paciente_id", "bitacora_tratamiento", ["paciente_id"])
    op.create_index("ix_bitacora_tratamiento_numero_diente", "bitacora_tratamiento", ["numero_diente"])
    op.create_index("ix_bitacora_tratamiento_tratamiento_id", "bitacora_tratamiento", ["tratamiento_id"])

    # --- 7. odontograma_hallazgo: activo -> resuelto + origen + tratamiento_id
    op.drop_column("odontograma_hallazgo", "activo")
    op.add_column(
        "odontograma_hallazgo",
        sa.Column("resuelto", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column("odontograma_hallazgo", "resuelto", server_default=None)
    op.add_column("odontograma_hallazgo", sa.Column("resuelto_fecha", sa.Date(), nullable=True))
    op.add_column(
        "odontograma_hallazgo",
        sa.Column(
            "resuelto_por_hallazgo_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("odontograma_hallazgo.id"),
            nullable=True,
        ),
    )
    op.add_column(
        "odontograma_hallazgo",
        sa.Column("origen", origen_hallazgo, nullable=False, server_default="aqui"),
    )
    op.alter_column("odontograma_hallazgo", "origen", server_default=None)
    op.add_column(
        "odontograma_hallazgo",
        sa.Column("tratamiento_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tratamiento.id"), nullable=True),
    )
    op.create_index("ix_odontograma_hallazgo_tratamiento_id", "odontograma_hallazgo", ["tratamiento_id"])

    # --- 8. observacion -----------------------------------------------
    op.create_table(
        "observacion",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("paciente_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("paciente.id"), nullable=False),
        sa.Column("visita_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("visita.id"), nullable=True),
        sa.Column("tipo", tipo_observacion, nullable=False),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("texto", sa.Text(), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("creado_por", postgresql.UUID(as_uuid=True), sa.ForeignKey("usuario.id"), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actualizado_por", postgresql.UUID(as_uuid=True), sa.ForeignKey("usuario.id"), nullable=True),
    )
    op.create_index("ix_observacion_paciente_id", "observacion", ["paciente_id"])


def downgrade() -> None:
    op.drop_table("observacion")

    op.drop_index("ix_odontograma_hallazgo_tratamiento_id", table_name="odontograma_hallazgo")
    op.drop_column("odontograma_hallazgo", "tratamiento_id")
    op.drop_column("odontograma_hallazgo", "origen")
    op.drop_column("odontograma_hallazgo", "resuelto_por_hallazgo_id")
    op.drop_column("odontograma_hallazgo", "resuelto_fecha")
    op.drop_column("odontograma_hallazgo", "resuelto")
    op.add_column(
        "odontograma_hallazgo",
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.alter_column("odontograma_hallazgo", "activo", server_default=None)

    op.drop_table("bitacora_tratamiento")
    op.drop_table("tratamiento_diente")
    op.drop_table("tratamiento")
    op.drop_table("profesional_tratante")

    op.drop_column("visita", "examen_tomografia")

    op.drop_table("paciente_antecedente")
    op.drop_table("antecedente")

    op.drop_column("paciente", "foto")
    op.drop_column("paciente", "documento_historia_anterior")
    op.drop_column("paciente", "historia_origen")
    op.drop_column("paciente", "fecha_primera_consulta_real")
    op.drop_constraint("uq_paciente_numero_historia", "paciente", type_="unique")
    op.drop_column("paciente", "numero_historia")

    bind = op.get_bind()
    for enum_type in reversed(NEW_ENUMS):
        enum_type.drop(bind, checkfirst=True)
