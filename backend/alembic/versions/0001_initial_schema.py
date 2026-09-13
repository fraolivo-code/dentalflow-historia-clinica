"""esquema inicial: usuario, paciente, visita y odontograma completo

Revision ID: 0001
Revises:
Create Date: 2026-09-12

Crea las tablas de la seccion 1 de la especificacion tecnica
(especificacion-tecnica-odontograma-fase2.md) mas las tablas de soporte
minimas (usuario, paciente, visita) acordadas para tener FK reales desde el
inicio. Incluye los campos de auditoria de la seccion 0.1 y siembra el
catalogo estatico diente_anatomia (seccion 1.1, cerrado).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---------------------------------------------------------------------------
# Enums nativos de Postgres. Se crean una vez aqui y se referencian con
# create_type=False en cada columna para no intentar recrearlos.
# ---------------------------------------------------------------------------

# create_type=False en todos: los tipos se crean/destruyen explicitamente en
# upgrade()/downgrade() (ver ALL_ENUMS mas abajo). Sin esto, SQLAlchemy emite
# un CREATE TYPE adicional (duplicado) cada vez que el enum se usa como tipo
# de columna en un create_table.
rol_usuario = postgresql.ENUM("dra", "asistente", "admin", name="rol_usuario", create_type=False)
higiene_bucal = postgresql.ENUM(
    "E", "B", "R", "M", "P", name="higiene_bucal", create_type=False
)
tipo_hallazgo = postgresql.ENUM(
    "sano",
    "ausente",
    "implante",
    "caries",
    "conducto_ok",
    "conducto_ok_perno",
    "conducto_defecto",
    "conducto_perno_defecto",
    "conducto_indicado",
    "corona_ok",
    "corona_defecto",
    "obturacion_ok",
    "obturacion_defecto",
    "resto_radicular",
    "diente_impactado",
    "exodoncia_simple",
    "exodoncia_quirurgica",
    "movimiento_extrusion",
    "movimiento_intrusion",
    "movimiento_mesializacion",
    "movimiento_distalizacion",
    "movimiento_rotacion",
    "spp",
    "carilla_ok",
    "carilla_defecto",
    "afraccion",
    name="tipo_hallazgo",
    create_type=False,
)
superficie_dental = postgresql.ENUM(
    "mesial",
    "distal",
    "oclusal",
    "vestibular",
    "cervical",
    name="superficie_dental",
    create_type=False,
)
tipo_lesion_apical = postgresql.ENUM(
    "periapical", "periimplantitis", name="tipo_lesion_apical", create_type=False
)
estado_general_puente = postgresql.ENUM(
    "ok", "defecto", name="estado_general_puente", create_type=False
)
rol_diente_puente = postgresql.ENUM(
    "pilar", "pontico", name="rol_diente_puente", create_type=False
)
tipo_consentimiento = postgresql.ENUM(
    "tratamiento", "almacenamiento_digital", name="tipo_consentimiento", create_type=False
)
sitio_periodontal = postgresql.ENUM(
    "mesiovestibular",
    "vestibular",
    "distovestibular",
    "distopalatino_lingual",
    "palatino_lingual",
    "mesiopalatino_lingual",
    name="sitio_periodontal",
    create_type=False,
)
furcacion_glickman = postgresql.ENUM(
    "I", "II", "III", name="furcacion_glickman", create_type=False
)

ALL_ENUMS = [
    rol_usuario,
    higiene_bucal,
    tipo_hallazgo,
    superficie_dental,
    tipo_lesion_apical,
    estado_general_puente,
    rol_diente_puente,
    tipo_consentimiento,
    sitio_periodontal,
    furcacion_glickman,
]

# Catalogo cerrado (seccion 1.1). No cambia.
DIENTE_ANATOMIA_SEED = [
    *[
        {"numero_diente": n, "num_raices": 1, "nombres_raices": ["Única"]}
        for n in (11, 12, 13, 21, 22, 23, 31, 32, 33, 41, 42, 43)
    ],
    *[
        {"numero_diente": n, "num_raices": 2, "nombres_raices": ["Vestibular", "Palatina"]}
        for n in (14, 24)
    ],
    *[
        {"numero_diente": n, "num_raices": 1, "nombres_raices": ["Única"]}
        for n in (15, 25, 34, 35, 44, 45)
    ],
    *[
        {
            "numero_diente": n,
            "num_raices": 3,
            "nombres_raices": ["Mesiovestibular", "Palatina", "Distovestibular"],
        }
        for n in (16, 17, 18, 26, 27, 28)
    ],
    *[
        {"numero_diente": n, "num_raices": 2, "nombres_raices": ["Mesial", "Distal"]}
        for n in (36, 37, 38, 46, 47, 48)
    ],
]


def upgrade() -> None:
    bind = op.get_bind()
    for enum_type in ALL_ENUMS:
        enum_type.create(bind, checkfirst=True)

    op.create_table(
        "usuario",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("nombre", sa.String(200), nullable=False),
        sa.Column("rol", rol_usuario, nullable=False),
        sa.Column("activo", sa.Boolean(), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "paciente",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("telefono_fijo", sa.String(50), nullable=True),
        sa.Column("movil", sa.String(50), nullable=False),
        sa.Column("nombre_completo", sa.String(300), nullable=False),
        sa.Column("fecha_nacimiento", sa.Date(), nullable=True),
        sa.Column("direccion", sa.Text(), nullable=True),
        sa.Column("email", sa.String(300), nullable=True),
        sa.Column("empresa_profesion_cargo", sa.String(300), nullable=True),
        sa.Column("referido_por", sa.String(300), nullable=False),
        sa.Column("fuma", sa.Boolean(), nullable=False),
        sa.Column("fuma_detalle", sa.Text(), nullable=True),
        sa.Column("medicamentos_actuales", sa.Boolean(), nullable=False),
        sa.Column("medicamentos_actuales_detalle", sa.Text(), nullable=True),
        sa.Column("tratamiento_medico_actual", sa.Text(), nullable=True),
        sa.Column("fecha_registro", sa.Date(), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("creado_por", postgresql.UUID(as_uuid=True), sa.ForeignKey("usuario.id"), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actualizado_por", postgresql.UUID(as_uuid=True), sa.ForeignKey("usuario.id"), nullable=True),
    )
    op.create_index("ix_paciente_movil", "paciente", ["movil"])

    op.create_table(
        "diente_anatomia",
        sa.Column("numero_diente", sa.SmallInteger(), primary_key=True, autoincrement=False),
        sa.Column("num_raices", sa.SmallInteger(), nullable=False),
        sa.Column("nombres_raices", postgresql.ARRAY(sa.String(50)), nullable=False),
        sa.CheckConstraint("num_raices IN (1, 2, 3)", name="ck_diente_anatomia_num_raices"),
    )

    op.create_table(
        "visita",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("paciente_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("paciente.id"), nullable=False),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("responsable", postgresql.UUID(as_uuid=True), sa.ForeignKey("usuario.id"), nullable=False),
        sa.Column("motivo_consulta", sa.Text(), nullable=True),
        sa.Column("examen_extraoral_atm", sa.Text(), nullable=True),
        sa.Column("examen_extraoral_ganglios", sa.Text(), nullable=True),
        sa.Column("examen_extraoral_otros", sa.Text(), nullable=True),
        sa.Column("higiene", higiene_bucal, nullable=False),
        sa.Column("tejidos_blandos", sa.Text(), nullable=True),
        sa.Column("examen_rx_periapical", sa.Boolean(), nullable=False),
        sa.Column("examen_ex_pc", sa.Boolean(), nullable=False),
        sa.Column("examen_rx_panoramica", sa.Boolean(), nullable=False),
        sa.Column("examen_rutina_quirurgica", sa.Boolean(), nullable=False),
        sa.Column("examen_otras", sa.Text(), nullable=True),
        sa.Column("hallazgos", sa.Text(), nullable=True),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("creado_por", postgresql.UUID(as_uuid=True), sa.ForeignKey("usuario.id"), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actualizado_por", postgresql.UUID(as_uuid=True), sa.ForeignKey("usuario.id"), nullable=True),
    )
    op.create_index("ix_visita_paciente_id", "visita", ["paciente_id"])

    op.create_table(
        "odontograma_hallazgo",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("paciente_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("paciente.id"), nullable=False),
        sa.Column("numero_diente", sa.SmallInteger(), sa.ForeignKey("diente_anatomia.numero_diente"), nullable=False),
        sa.Column("visita_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("visita.id"), nullable=True),
        sa.Column("tipo_hallazgo", tipo_hallazgo, nullable=False),
        sa.Column("superficie", superficie_dental, nullable=True),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("activo", sa.Boolean(), nullable=False),
        sa.Column("notas", sa.Text(), nullable=True),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("creado_por", postgresql.UUID(as_uuid=True), sa.ForeignKey("usuario.id"), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actualizado_por", postgresql.UUID(as_uuid=True), sa.ForeignKey("usuario.id"), nullable=True),
    )
    op.create_index("ix_odontograma_hallazgo_paciente_id", "odontograma_hallazgo", ["paciente_id"])
    op.create_index("ix_odontograma_hallazgo_numero_diente", "odontograma_hallazgo", ["numero_diente"])

    op.create_table(
        "odontograma_lesion_apical",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("paciente_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("paciente.id"), nullable=False),
        sa.Column("numero_diente", sa.SmallInteger(), sa.ForeignKey("diente_anatomia.numero_diente"), nullable=False),
        sa.Column("visita_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("visita.id"), nullable=True),
        sa.Column("raiz", sa.String(50), nullable=False),
        sa.Column("tipo", tipo_lesion_apical, nullable=False),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("creado_por", postgresql.UUID(as_uuid=True), sa.ForeignKey("usuario.id"), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actualizado_por", postgresql.UUID(as_uuid=True), sa.ForeignKey("usuario.id"), nullable=True),
    )
    op.create_index("ix_odontograma_lesion_apical_paciente_id", "odontograma_lesion_apical", ["paciente_id"])
    op.create_index("ix_odontograma_lesion_apical_numero_diente", "odontograma_lesion_apical", ["numero_diente"])

    op.create_table(
        "puente_fijo",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("paciente_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("paciente.id"), nullable=False),
        sa.Column("visita_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("visita.id"), nullable=True),
        sa.Column("estado_general", estado_general_puente, nullable=False),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("creado_por", postgresql.UUID(as_uuid=True), sa.ForeignKey("usuario.id"), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actualizado_por", postgresql.UUID(as_uuid=True), sa.ForeignKey("usuario.id"), nullable=True),
    )
    op.create_index("ix_puente_fijo_paciente_id", "puente_fijo", ["paciente_id"])

    op.create_table(
        "puente_fijo_diente",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("puente_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("puente_fijo.id"), nullable=False),
        sa.Column("numero_diente", sa.SmallInteger(), sa.ForeignKey("diente_anatomia.numero_diente"), nullable=False),
        sa.Column("rol", rol_diente_puente, nullable=False),
        sa.Column("condicion_individual", tipo_hallazgo, nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("creado_por", postgresql.UUID(as_uuid=True), sa.ForeignKey("usuario.id"), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actualizado_por", postgresql.UUID(as_uuid=True), sa.ForeignKey("usuario.id"), nullable=True),
        sa.CheckConstraint(
            "condicion_individual IN ("
            "'sano','ausente','implante','conducto_ok','conducto_ok_perno',"
            "'conducto_defecto','conducto_perno_defecto','conducto_indicado'"
            ")",
            name="ck_puente_fijo_diente_condicion_individual",
        ),
    )
    op.create_index("ix_puente_fijo_diente_puente_id", "puente_fijo_diente", ["puente_id"])
    op.create_index("ix_puente_fijo_diente_numero_diente", "puente_fijo_diente", ["numero_diente"])

    op.create_table(
        "periodontograma_registro",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("paciente_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("paciente.id"), nullable=False),
        sa.Column("visita_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("visita.id"), nullable=False),
        sa.Column("numero_diente", sa.SmallInteger(), sa.ForeignKey("diente_anatomia.numero_diente"), nullable=False),
        sa.Column("sitio", sitio_periodontal, nullable=False),
        sa.Column("margen_gingival", sa.SmallInteger(), nullable=False),
        sa.Column("profundidad_sondaje", sa.SmallInteger(), nullable=False),
        sa.Column("nivel_insercion", sa.SmallInteger(), nullable=False),
        sa.Column("recesion_mm", sa.SmallInteger(), nullable=False),
        sa.Column("sangrado", sa.Boolean(), nullable=False),
        sa.Column("placa", sa.Boolean(), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("creado_por", postgresql.UUID(as_uuid=True), sa.ForeignKey("usuario.id"), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actualizado_por", postgresql.UUID(as_uuid=True), sa.ForeignKey("usuario.id"), nullable=True),
    )
    op.create_index("ix_periodontograma_registro_paciente_id", "periodontograma_registro", ["paciente_id"])
    op.create_index("ix_periodontograma_registro_visita_id", "periodontograma_registro", ["visita_id"])
    op.create_index("ix_periodontograma_registro_numero_diente", "periodontograma_registro", ["numero_diente"])

    op.create_table(
        "periodontograma_diente_resumen",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("paciente_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("paciente.id"), nullable=False),
        sa.Column("visita_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("visita.id"), nullable=False),
        sa.Column("numero_diente", sa.SmallInteger(), sa.ForeignKey("diente_anatomia.numero_diente"), nullable=False),
        sa.Column("movilidad", sa.SmallInteger(), nullable=False),
        sa.Column("furcacion", furcacion_glickman, nullable=True),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("creado_por", postgresql.UUID(as_uuid=True), sa.ForeignKey("usuario.id"), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actualizado_por", postgresql.UUID(as_uuid=True), sa.ForeignKey("usuario.id"), nullable=True),
        sa.CheckConstraint("movilidad BETWEEN 0 AND 3", name="ck_periodontograma_movilidad"),
    )
    op.create_index("ix_periodontograma_diente_resumen_paciente_id", "periodontograma_diente_resumen", ["paciente_id"])
    op.create_index("ix_periodontograma_diente_resumen_visita_id", "periodontograma_diente_resumen", ["visita_id"])
    op.create_index("ix_periodontograma_diente_resumen_numero_diente", "periodontograma_diente_resumen", ["numero_diente"])

    op.create_table(
        "consentimiento",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("paciente_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("paciente.id"), nullable=False),
        sa.Column("tipo", tipo_consentimiento, nullable=False),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("archivo", sa.String(1000), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("creado_por", postgresql.UUID(as_uuid=True), sa.ForeignKey("usuario.id"), nullable=False),
    )
    op.create_index("ix_consentimiento_paciente_id", "consentimiento", ["paciente_id"])

    diente_anatomia_table = sa.table(
        "diente_anatomia",
        sa.column("numero_diente", sa.SmallInteger()),
        sa.column("num_raices", sa.SmallInteger()),
        sa.column("nombres_raices", postgresql.ARRAY(sa.String(50))),
    )
    op.bulk_insert(diente_anatomia_table, DIENTE_ANATOMIA_SEED)


def downgrade() -> None:
    op.drop_table("consentimiento")
    op.drop_table("periodontograma_diente_resumen")
    op.drop_table("periodontograma_registro")
    op.drop_table("puente_fijo_diente")
    op.drop_table("puente_fijo")
    op.drop_table("odontograma_lesion_apical")
    op.drop_table("odontograma_hallazgo")
    op.drop_table("visita")
    op.drop_table("diente_anatomia")
    op.drop_table("paciente")
    op.drop_table("usuario")

    bind = op.get_bind()
    for enum_type in reversed(ALL_ENUMS):
        enum_type.drop(bind, checkfirst=True)
