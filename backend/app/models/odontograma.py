# app/models/odontograma.py — Seccion 1 de la especificacion tecnica.

import uuid
from datetime import date

from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    Date,
    Enum,
    ForeignKey,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.enums import (
    EstadoGeneralPuente,
    OrigenHallazgo,
    RolDientePuente,
    SuperficieDental,
    TipoHallazgo,
    TipoLesionApical,
)
from app.models.common import AuditMixin, UUIDPk


class DienteAnatomia(Base):
    """
    1.1 — Catalogo estatico, no depende del paciente. Cerrado, no debe
    cambiar. Sin campos de auditoria: no es una tabla clinica, es un catalogo
    de referencia (igual que la seccion 0.1 lo excluye implicitamente al no
    mencionarlo en su lista).
    """

    __tablename__ = "diente_anatomia"

    # autoincrement=False: es un codigo fijo (notacion FDI), no un id generado.
    numero_diente: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=False)
    num_raices: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    nombres_raices: Mapped[list[str]] = mapped_column(ARRAY(String(50)), nullable=False)

    __table_args__ = (
        CheckConstraint("num_raices IN (1, 2, 3)", name="ck_diente_anatomia_num_raices"),
    )


class OdontogramaHallazgo(Base, UUIDPk, AuditMixin):
    """1.2 — Hallazgos combinables por diente: una fila por hallazgo activo."""

    __tablename__ = "odontograma_hallazgo"

    paciente_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("paciente.id"), nullable=False, index=True
    )
    numero_diente: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("diente_anatomia.numero_diente"), nullable=False, index=True
    )
    visita_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("visita.id"), nullable=True
    )
    tipo_hallazgo: Mapped[TipoHallazgo] = mapped_column(
        Enum(TipoHallazgo, name="tipo_hallazgo", native_enum=True), nullable=False
    )
    superficie: Mapped[SuperficieDental | None] = mapped_column(
        Enum(SuperficieDental, name="superficie_dental", native_enum=True), nullable=True
    )
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    # Etapa 3, seccion 7: reemplaza a `activo`. resuelto=True cierra el
    # hallazgo (equivalente al viejo activo=False) pero ahora con el detalle
    # de cuando y por cual hallazgo nuevo quedo resuelto, en vez de un simple
    # booleano — nunca se borra el historico.
    resuelto: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    resuelto_fecha: Mapped[date | None] = mapped_column(Date, nullable=True)
    resuelto_por_hallazgo_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("odontograma_hallazgo.id"), nullable=True
    )
    # Distingue un hallazgo registrado aqui de uno que el paciente ya traia
    # (remitido por seguro, etc.).
    origen: Mapped[OrigenHallazgo] = mapped_column(
        Enum(OrigenHallazgo, name="origen_hallazgo", native_enum=True), nullable=False
    )
    # Vinculo con el tratamiento multisesion del que este hallazgo forma
    # parte (regla de creacion automatica, seccion 7 de la especificacion de
    # formularios). Nullable: no todo hallazgo viene de un tratamiento.
    tratamiento_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tratamiento.id"), nullable=True, index=True
    )
    notas: Mapped[str | None] = mapped_column(Text, nullable=True)


class OdontogramaLesionApical(Base, UUIDPk, AuditMixin):
    """
    1.3 — Lesion periapical / periimplantitis, independiente de
    odontograma_hallazgo. Se combina con cualquier estado, incluido "sano".
    Unica excepcion (23/09/2026): cargar "implante" o "ausente" cierra las
    periapicales del diente, y cerrar el implante cierra la periimplantitis
    (ver aplicar_hallazgo).
    """

    __tablename__ = "odontograma_lesion_apical"

    paciente_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("paciente.id"), nullable=False, index=True
    )
    numero_diente: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("diente_anatomia.numero_diente"), nullable=False, index=True
    )
    visita_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("visita.id"), nullable=True
    )
    # Debe coincidir con uno de los nombres_raices de diente_anatomia para ese
    # diente, o "Periimplantitis" si el diente tiene el hallazgo "implante"
    # activo. No se modela como FK: nombres_raices vive dentro de un array,
    # no en filas propias — se valida en la capa de aplicacion.
    raiz: Mapped[str] = mapped_column(String(50), nullable=False)
    tipo: Mapped[TipoLesionApical] = mapped_column(
        Enum(TipoLesionApical, name="tipo_lesion_apical", native_enum=True), nullable=False
    )
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    # 23/09/2026 (migracion 0008): mismo patron que odontograma_hallazgo —
    # cerrar sin borrar el historico. resuelto_por_hallazgo_id queda NULL en
    # un cierre manual (PATCH .../resolver) y apunta al hallazgo que lo
    # provoco en un cierre automatico (implante/ausente).
    resuelto: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    resuelto_fecha: Mapped[date | None] = mapped_column(Date, nullable=True)
    resuelto_por_hallazgo_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("odontograma_hallazgo.id"), nullable=True
    )


class PuenteFijo(Base, UUIDPk, AuditMixin):
    """
    1.4 — Un puente es una relacion entre varios dientes. Se cierra sin
    borrarse (resuelto=True, migracion 0009); mientras esta activo, la
    condicion de cada diente se define aqui y no en odontograma_hallazgo.
    """

    __tablename__ = "puente_fijo"

    paciente_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("paciente.id"), nullable=False, index=True
    )
    visita_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("visita.id"), nullable=True
    )
    estado_general: Mapped[EstadoGeneralPuente] = mapped_column(
        Enum(EstadoGeneralPuente, name="estado_general_puente", native_enum=True), nullable=False
    )
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    resuelto: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    resuelto_fecha: Mapped[date | None] = mapped_column(Date, nullable=True)


class PuenteFijoDiente(Base, UUIDPk, AuditMixin):
    """
    1.4 — Un diente dentro de un puente, con su propia condicion individual
    (subconjunto de tipo_hallazgo, ver CONDICION_INDIVIDUAL_PUENTE_VALIDAS en
    app/enums.py), independiente del estado_general de la protesis.
    """

    __tablename__ = "puente_fijo_diente"

    puente_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("puente_fijo.id"), nullable=False, index=True
    )
    numero_diente: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("diente_anatomia.numero_diente"), nullable=False, index=True
    )
    rol: Mapped[RolDientePuente] = mapped_column(
        Enum(RolDientePuente, name="rol_diente_puente", native_enum=True), nullable=False
    )
    condicion_individual: Mapped[TipoHallazgo] = mapped_column(
        Enum(TipoHallazgo, name="tipo_hallazgo", native_enum=True, create_type=False),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "condicion_individual IN ("
            "'sano','ausente','implante','conducto_ok','conducto_ok_perno',"
            "'conducto_defecto','conducto_perno_defecto','conducto_indicado'"
            ")",
            name="ck_puente_fijo_diente_condicion_individual",
        ),
        # Regla rol <-> condicion (24/09/2026, migracion 0009).
        CheckConstraint(
            "(rol = 'pontico') = (condicion_individual = 'ausente')",
            name="ck_puente_fijo_diente_rol_condicion",
        ),
    )
