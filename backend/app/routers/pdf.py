from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_usuario, get_session, requerir_acceso_total, requerir_dra
from app.routers.pacientes import obtener_paciente_o_404
from app.services import odontograma_impreso as impreso
from app.services.consultorio import membrete_consultorio
from app.services.fechas import hoy_venezuela
from app.services.odontograma_svg import MODO_BLANCO, MODO_COLOR, odontograma_svg
from app.services.pdf import generar_pdf

# Documentos PDF con datos del paciente: solo dra (igual que visitas,
# odontograma y periodontograma), por endpoint. Los impresos EN BLANCO
# (formulario de ingreso y odontograma en blanco) no llevan datos de nadie y los
# imprime cualquier usuario autenticado (04/10/2026).
router = APIRouter(tags=["pdf"])


def _odontograma_en_blanco() -> dict:
    return {
        "svg": odontograma_svg([], [], [], {}, MODO_BLANCO),
        "lineas": impreso.lineas_por_diente(),
        "plan": [],
    }


@router.get("/pacientes/{paciente_id}/pdf/prueba", dependencies=[Depends(requerir_dra)])
async def pdf_prueba(paciente_id: UUID, session: AsyncSession = Depends(get_session)):
    """
    PDF de humo (25/09/2026): valida la tuberia WeasyPrint + fuentes de marca
    en produccion antes de disenar los documentos reales. Solo usa el nombre
    del paciente.
    """
    paciente = await obtener_paciente_o_404(paciente_id, session)
    pdf = await generar_pdf(
        "prueba.html",
        {
            "nombre_paciente": paciente.nombre_completo,
            "fecha": hoy_venezuela().strftime("%d/%m/%Y"),
        },
    )
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="prueba-{paciente.numero_historia}.pdf"'
        },
    )


# Mismas 10 categorias y mismo orden que el catalogo `antecedente` (Etapa 3,
# seccion 2), fijas en el papel: (nombre, pista del detalle, renglones). La
# pista marca las que llevan linea de detalle: las 3 con requiere_detalle en
# el catalogo, mas Alergias y Otras (solo espacio extra en el papel, aprobado
# 26/09/2026; el catalogo no cambia). Operaciones lleva 2 renglones: suele
# ser mas de una, cada una con su fecha.
ANTECEDENTES_FORMULARIO = (
    ("Diabetes", None, 0),
    ("Hepatitis", "Tipo:", 1),
    ("E. Cardíaca", None, 0),
    ("Tensión", None, 0),
    ("Herpes", None, 0),
    ("Alergias", "¿A qué?", 1),
    ("Traumatismos faciales", None, 0),
    ("Convulsiones", "¿Cuándo?", 1),
    ("Operaciones", "¿Qué y cuándo?", 2),
    ("Otras", "¿Cuáles?", 1),
)


@router.get("/pdf/formulario-ingreso", dependencies=[Depends(get_current_usuario)])
async def pdf_formulario_ingreso(session: AsyncSession = Depends(get_session)):
    """
    Formulario de ingreso EN BLANCO (Documento 4 de 5), para llenar a mano
    mientras la Dra. sigue en papel y transcribir despues 1 a 1 a la ficha
    digital. Pagina 2: odontograma en blanco. Standalone: no depende de ningun
    paciente; el membrete sale de la configuracion del consultorio (no del
    profesional del usuario), asi que no exige profesional vinculado.
    """
    pdf = await generar_pdf(
        "formulario_ingreso.html",
        {
            "membrete": await membrete_consultorio(session),
            "antecedentes": ANTECEDENTES_FORMULARIO,
            "odontograma": _odontograma_en_blanco(),
        },
    )
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": 'inline; filename="formulario-ingreso.pdf"'},
    )


@router.get("/pdf/odontograma-blanco", dependencies=[Depends(get_current_usuario)])
async def pdf_odontograma_blanco(session: AsyncSession = Depends(get_session)):
    """Solo la hoja del odontograma en blanco, con espacio para nombre, N.° de historia y fecha."""
    pdf = await generar_pdf(
        "odontograma_blanco.html",
        {"membrete": await membrete_consultorio(session), "odontograma": _odontograma_en_blanco()},
    )
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": 'inline; filename="odontograma-blanco.pdf"'},
    )


@router.get(
    "/pacientes/{paciente_id}/pdf/odontograma-actual", dependencies=[Depends(requerir_acceso_total)]
)
async def pdf_odontograma_actual(paciente_id: UUID, session: AsyncSession = Depends(get_session)):
    """
    Odontograma actual para llevar a la consulta: el dibujo a color (igual que
    la historia completa: en gris no se distingue una caries de una
    restauracion) y, en gris, las lineas por diente con lo registrado y el plan
    de tratamiento con los tratamientos activos. Lo nuevo se anota a mano, tambien
    en la linea de su diente. Solo acceso total.
    """
    paciente = await obtener_paciente_o_404(paciente_id, session)
    estado = await impreso.cargar_estado(session, paciente_id)
    activos = [h for h in estado["hallazgos"] if not h.resuelto]
    lesiones = [l for l in estado["lesiones"] if not l.resuelto]
    puentes = [(p, estado["dientes_de"][p.id]) for p in estado["puentes"] if not p.resuelto]
    leyenda = impreso.leyenda_por_diente(activos, lesiones, puentes)
    hoy = hoy_venezuela()

    pdf = await generar_pdf(
        "odontograma_actual.html",
        {
            "membrete": await membrete_consultorio(session),
            "paciente": paciente,
            "fecha_impresion": hoy,
            "odontograma": {
                "svg": odontograma_svg(activos, lesiones, puentes, estado["raices"], MODO_COLOR),
                "lineas": impreso.lineas_por_diente(leyenda),
                "plan": await impreso.plan_de_tratamiento(session, paciente_id),
            },
        },
    )
    nombre = f"odontograma-actual-{paciente.numero_historia}-{hoy.isoformat()}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{nombre}"'},
    )
