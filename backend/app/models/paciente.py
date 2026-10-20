# app/models/paciente.py — Version minima acordada para tener FK reales desde
# el odontograma. Definida a partir de lo ya conversado con la Dra. en el
# proceso (proceso-automatizacion-odontologo-v2.md), no es el cierre formal
# completo de la Etapa 1: se espera ampliar (antecedentes estructurados via
# `antecedente`/`paciente_antecedente`, etc.) sin romper este esquema base.

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Index, String, Text, false, text, true
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, validates

from app.db import Base
from app.enums import Denticion, EstadoHistoria
from app.models.common import AuditMixin, UUIDPk
from app.services.movil import normalizar_movil


class Paciente(Base, UUIDPk, AuditMixin):
    __tablename__ = "paciente"
    __table_args__ = (
        Index(
            "uq_paciente_cedula",
            "cedula",
            unique=True,
            postgresql_where=text("cedula IS NOT NULL"),
            sqlite_where=text("cedula IS NOT NULL"),
        ),
    )

    # Correlativo generado por el sistema, no basado en cedula (Etapa 3, seccion 1)
    # — evita el caso de menores u otros pacientes sin documento.
    numero_historia: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    telefono_fijo: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # Llave de vinculacion con Alma (fase1-whatsapp-bot): mismo numero de WhatsApp.
    movil: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    # Etapa 6: movil en formato 58XXXXXXXXXX (o None si no encaja), para cruzar con
    # el numero de WhatsApp de Alma. Se recalcula solo al asignar `movil` (ver
    # _calcular_movil_normalizado); no es unico.
    movil_normalizado: Mapped[str | None] = mapped_column(String(15), nullable=True, index=True)
    nombre_completo: Mapped[str] = mapped_column(String(300), nullable=False)
    # Opcional (25/09/2026): se imprime en la constancia de asistencia si existe.
    # Unica entre las que tienen valor (indice parcial uq_paciente_cedula, migracion 0028).
    cedula: Mapped[str | None] = mapped_column(String(20), nullable=True)
    cedula_representante: Mapped[str | None] = mapped_column(String(20), nullable=True)
    fecha_nacimiento: Mapped[date | None] = mapped_column(Date, nullable=True)
    direccion: Mapped[str | None] = mapped_column(Text, nullable=True)
    email: Mapped[str | None] = mapped_column(String(300), nullable=True)
    empresa_profesion_cargo: Mapped[str | None] = mapped_column(String(300), nullable=True)
    # "N/A" para pacientes ya existentes transcritos sin este dato (confirmado con la Dra.).
    referido_por: Mapped[str] = mapped_column(String(300), nullable=False, default="N/A")
    fuma: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    fuma_detalle: Mapped[str | None] = mapped_column(Text, nullable=True)
    medicamentos_actuales: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    medicamentos_actuales_detalle: Mapped[str | None] = mapped_column(Text, nullable=True)
    tratamiento_medico_actual: Mapped[str | None] = mapped_column(Text, nullable=True)
    fecha_registro: Mapped[date] = mapped_column(Date, nullable=False)

    # Etapa 3, seccion 1: caso del paciente remitido por seguro que regresa
    # tiempo despues a pagar por su cuenta — el correlativo de este consultorio
    # se le asigna ahora, pero su primera atencion real fue antes.
    fecha_primera_consulta_real: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Solo tiene sentido si se lleno fecha_primera_consulta_real.
    historia_origen: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Referencia a archivo (mismo patron que consentimiento.archivo): solo la
    # ruta/clave del objeto, sin logica de storage real conectada todavia
    # (Cloudflare R2, pendiente de credenciales — ver especificacion seccion 1.1).
    documento_historia_anterior: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    foto: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    # Texto libre y opcional (04/10/2026); sin lista de aseguradoras.
    seguro: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # Texto libre y opcional (06/10/2026), solo en el ingreso: "hace 2 anos", etc.
    ultima_visita_odontologo: Mapped[str | None] = mapped_column(String(120), nullable=True)

    # Historia en carga / aprobada (migracion 0033, 15/10/2026). Toda ficha nueva nace «en_carga»;
    # solo la Dra. (cuenta vinculada a su profesional) la aprueba. Las fichas que ya existian
    # quedaron «aprobada».
    estado_historia: Mapped[EstadoHistoria] = mapped_column(
        Enum(
            EstadoHistoria,
            name="estado_historia",
            native_enum=True,
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
        default=EstadoHistoria.en_carga,
        server_default="en_carga",
    )
    aprobada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    aprobada_por: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("usuario.id"), nullable=True
    )
    # Odontograma mixto (migracion 0034, 15/10/2026): que dientes muestra el odontograma. Lo cambian
    # la Dra. o Francisco; al crear la ficha se sugiere «mixta» hasta los 12 anos.
    denticion: Mapped[Denticion] = mapped_column(
        Enum(
            Denticion,
            name="denticion",
            native_enum=True,
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
        default=Denticion.adulta,
        server_default="adulta",
    )

    # Migracion 0035 (17/10/2026). La Dra. decide a criterio propio que paciente requiere alerta
    # (marcapasos, anticoagulantes, alergias...) y escribe de que se trata; se ve sin abrir la historia.
    alerta: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())
    alerta_texto: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Solo con diagnostico periodontal: decide si se ofrece el periodontograma.
    seguimiento_periodontal: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    # Baja explicita (cambio de odontologo, etc.); sin ella siempre se le recuerda su control.
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=true())
    motivo_inactivo: Mapped[str | None] = mapped_column(Text, nullable=True)

    @property
    def paciente_desde(self) -> int:
        """Anio de la primera consulta real; si falta, el de la creacion (calculado)."""
        if self.fecha_primera_consulta_real is not None:
            return self.fecha_primera_consulta_real.year
        if self.creado_en is not None:
            return self.creado_en.year
        return self.fecha_registro.year

    @validates("movil")
    def _calcular_movil_normalizado(self, _clave: str, valor: str) -> str:
        # Unico lugar donde se calcula: cubre la creacion y cada edicion de `movil`.
        self.movil_normalizado = normalizar_movil(valor)
        return valor
