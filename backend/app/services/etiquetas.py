# app/services/etiquetas.py — Texto legible (el que ve el paciente en un PDF)
# de los valores internos de los enums.

from app.enums import (
    EstadoTratamiento,
    HigieneBucal,
    OrigenTratamiento,
    SuperficieDental,
    TipoConsentimiento,
    TipoHallazgo,
    TipoObservacion,
)

ESTADO_TRATAMIENTO = {
    EstadoTratamiento.indicado: "Indicado",
    EstadoTratamiento.en_curso: "En curso",
    EstadoTratamiento.completado: "Completado",
    EstadoTratamiento.suspendido: "Suspendido",
}

ORIGEN_TRATAMIENTO = {
    OrigenTratamiento.aqui: "En este consultorio",
    OrigenTratamiento.remitido_externo: "Remitido a profesional externo",
}

HIGIENE = {
    HigieneBucal.excelente: "Excelente",
    HigieneBucal.buena: "Buena",
    HigieneBucal.regular: "Regular",
    HigieneBucal.mala: "Mala",
    HigieneBucal.pesima: "Pésima",
}

TIPO_CONSENTIMIENTO = {
    TipoConsentimiento.tratamiento: "Consentimiento de tratamiento",
    TipoConsentimiento.almacenamiento_digital: "Autorización de almacenamiento digital de datos",
}

TIPO_OBSERVACION = {
    TipoObservacion.clinica: "Clínica",
    TipoObservacion.administrativa: "Administrativa",
    TipoObservacion.otra: "Otra",
}

SUPERFICIE = {
    SuperficieDental.mesial: "mesial",
    SuperficieDental.distal: "distal",
    SuperficieDental.oclusal: "oclusal",
    SuperficieDental.vestibular: "vestibular",
    SuperficieDental.cervical: "cervical",
}

# Mismas etiquetas que ve la Dra. en pantalla (CATALOGO de
# components/Odontograma/catalogo.ts del frontend), para que el documento
# diga lo mismo que la app. Excepcion: las que en el dibujo se marcan con
# letras llevan la abreviatura, asi la leyenda explica el simbolo.
HALLAZGO = {
    TipoHallazgo.sano: "Sano",
    TipoHallazgo.ausente: "Ausente",
    TipoHallazgo.implante: "Implante",
    TipoHallazgo.conducto_ok: "Conducto en buen estado",
    TipoHallazgo.conducto_ok_perno: "Conducto con perno, buen estado",
    TipoHallazgo.conducto_defecto: "Conducto con defecto",
    TipoHallazgo.conducto_perno_defecto: "Conducto con perno, con defecto",
    TipoHallazgo.conducto_indicado: "Conducto indicado",
    TipoHallazgo.caries: "Caries",
    TipoHallazgo.obturacion_ok: "Obturación en buen estado",
    TipoHallazgo.obturacion_defecto: "Obturación con defecto",
    TipoHallazgo.corona_ok: "Corona en buen estado",
    TipoHallazgo.corona_defecto: "Corona con defecto",
    TipoHallazgo.carilla_ok: "Carilla en buen estado",
    TipoHallazgo.carilla_defecto: "Carilla con defecto",
    TipoHallazgo.afraccion: "Afracción",
    TipoHallazgo.diente_impactado: "Diente impactado",
    TipoHallazgo.movimiento_extrusion: "Extrusión",
    TipoHallazgo.movimiento_intrusion: "Intrusión",
    TipoHallazgo.movimiento_mesializacion: "Mesialización",
    TipoHallazgo.movimiento_distalizacion: "Distalización",
    TipoHallazgo.movimiento_rotacion: "Rotación",
    TipoHallazgo.diastema: "Diastema",
    TipoHallazgo.resto_radicular: "Resto radicular (RR)",
    TipoHallazgo.exodoncia_simple: "Exodoncia simple (S)",
    TipoHallazgo.exodoncia_quirurgica: "Exodoncia quirúrgica (Q)",
    TipoHallazgo.spp: "Superficie prepatogénica (SPP)",
}


# Examen complementario de la visita: (columna booleana, etiqueta del papel).
EXAMENES_COMPLEMENTARIOS = (
    ("examen_rx_periapical", "Rx periapical"),
    ("examen_ex_pc", "Ex. P.C."),
    ("examen_rx_panoramica", "Rx panorámica"),
    ("examen_rutina_quirurgica", "Rutina quirúrgica"),
    ("examen_tomografia", "Tomografía"),
)
