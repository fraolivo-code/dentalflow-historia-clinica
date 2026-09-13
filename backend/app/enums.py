# app/enums.py — Catalogos fijos (no editables) del odontograma y del resto
# del esquema clinico.
#
# tipo_hallazgo es "lista fija, no catalogo editable" (seccion 2.1 de la
# especificacion): se modela como Postgres ENUM nativo, no como tabla aparte.
# El agrupamiento (exclusive/endo/independent) que define las reglas de
# exclusividad (seccion 3.3) NO se guarda en la base — es logica de
# aplicacion/UI, tal como especifica el documento. Se deja aqui, junto al
# enum, como unica fuente de verdad para esa logica cuando se construya la API.

import enum

# Notacion FDI, dientes permanentes (seccion 1.1 de la especificacion). Se usa
# para validar numero_diente en la capa de API con un mensaje claro, antes de
# depender del error crudo de la FK contra diente_anatomia.
NUMEROS_DIENTE_VALIDOS = frozenset(
    {11, 12, 13, 14, 15, 16, 17, 18}
    | {21, 22, 23, 24, 25, 26, 27, 28}
    | {31, 32, 33, 34, 35, 36, 37, 38}
    | {41, 42, 43, 44, 45, 46, 47, 48}
)


class RolUsuario(str, enum.Enum):
    dra = "dra"
    asistente = "asistente"
    admin = "admin"


class HigieneBucal(str, enum.Enum):
    """Escala E/B/R/M/P confirmada para el examen de visita."""

    excelente = "E"
    buena = "B"
    regular = "R"
    mala = "M"
    pesima = "P"


class TipoHallazgo(str, enum.Enum):
    sano = "sano"
    ausente = "ausente"
    implante = "implante"
    caries = "caries"
    conducto_ok = "conducto_ok"
    conducto_ok_perno = "conducto_ok_perno"
    conducto_defecto = "conducto_defecto"
    conducto_perno_defecto = "conducto_perno_defecto"
    conducto_indicado = "conducto_indicado"
    corona_ok = "corona_ok"
    corona_defecto = "corona_defecto"
    obturacion_ok = "obturacion_ok"
    obturacion_defecto = "obturacion_defecto"
    resto_radicular = "resto_radicular"
    diente_impactado = "diente_impactado"
    exodoncia_simple = "exodoncia_simple"
    exodoncia_quirurgica = "exodoncia_quirurgica"
    movimiento_extrusion = "movimiento_extrusion"
    movimiento_intrusion = "movimiento_intrusion"
    movimiento_mesializacion = "movimiento_mesializacion"
    movimiento_distalizacion = "movimiento_distalizacion"
    movimiento_rotacion = "movimiento_rotacion"
    spp = "spp"
    carilla_ok = "carilla_ok"
    carilla_defecto = "carilla_defecto"
    afraccion = "afraccion"


# Grupos de exclusividad (seccion 1.2 / 3.3). Logica de aplicacion, no de la
# base de datos.
GRUPO_EXCLUSIVE = {TipoHallazgo.sano, TipoHallazgo.ausente, TipoHallazgo.implante}
GRUPO_ENDO = {
    TipoHallazgo.conducto_ok,
    TipoHallazgo.conducto_ok_perno,
    TipoHallazgo.conducto_defecto,
    TipoHallazgo.conducto_perno_defecto,
    TipoHallazgo.conducto_indicado,
}
# Todo lo que no esta en GRUPO_EXCLUSIVE ni GRUPO_ENDO pertenece a "independent".

# Subconjunto valido de tipo_hallazgo para puente_fijo_diente.condicion_individual
# (seccion 1.4): sano, los 5 estados de endo, implante, ausente. Fuente unica
# de verdad (los valores, como strings) para el enum angosto de Pydantic
# (CondicionIndividualPuente, capa de schema) y para CONDICION_INDIVIDUAL_PUENTE_VALIDAS
# (capa de servicio) — evita que las dos listas se desincronicen.
_CONDICION_INDIVIDUAL_PUENTE_VALORES = (
    "sano",
    "ausente",
    "implante",
    "conducto_ok",
    "conducto_ok_perno",
    "conducto_defecto",
    "conducto_perno_defecto",
    "conducto_indicado",
)


class CondicionIndividualPuente(str, enum.Enum):
    """
    Mismos 8 valores que TipoHallazgo, como tipo propio para que
    puente_fijo_diente.condicion_individual quede restringido ya en el
    schema de request (capa 1), no solo en el servicio (capa 2) y el CHECK
    de la base (capa 3) — las tres capas deben rechazar el mismo dato
    invalido, no solo la ultima.
    """

    sano = "sano"
    ausente = "ausente"
    implante = "implante"
    conducto_ok = "conducto_ok"
    conducto_ok_perno = "conducto_ok_perno"
    conducto_defecto = "conducto_defecto"
    conducto_perno_defecto = "conducto_perno_defecto"
    conducto_indicado = "conducto_indicado"


CONDICION_INDIVIDUAL_PUENTE_VALIDAS = frozenset(
    TipoHallazgo(v) for v in _CONDICION_INDIVIDUAL_PUENTE_VALORES
)


class SuperficieDental(str, enum.Enum):
    mesial = "mesial"
    distal = "distal"
    oclusal = "oclusal"
    vestibular = "vestibular"
    cervical = "cervical"


class TipoLesionApical(str, enum.Enum):
    periapical = "periapical"
    periimplantitis = "periimplantitis"


class EstadoGeneralPuente(str, enum.Enum):
    ok = "ok"
    defecto = "defecto"


class RolDientePuente(str, enum.Enum):
    pilar = "pilar"
    pontico = "pontico"


class TipoConsentimiento(str, enum.Enum):
    tratamiento = "tratamiento"
    almacenamiento_digital = "almacenamiento_digital"


class SitioPeriodontal(str, enum.Enum):
    """
    6 sitios por diente (estandar perio-tools.com / Universidad de Berna,
    seccion 1.5). Nomenclatura generica vestibular/palatino-lingual
    pendiente de confirmar con la Dra. junto con el resto de la UI del
    periodontograma.
    """

    mesiovestibular = "mesiovestibular"
    vestibular = "vestibular"
    distovestibular = "distovestibular"
    distopalatino_lingual = "distopalatino_lingual"
    palatino_lingual = "palatino_lingual"
    mesiopalatino_lingual = "mesiopalatino_lingual"


class FurcacionGlickman(str, enum.Enum):
    """Grados I-III. Solo aplica a molares (columna nullable)."""

    grado_i = "I"
    grado_ii = "II"
    grado_iii = "III"
