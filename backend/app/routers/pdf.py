from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_usuario, get_session, requerir_dra
from app.models.usuario import Usuario
from app.routers.constancias_asistencia import profesional_del_usuario
from app.routers.pacientes import obtener_paciente_o_404
from app.services.fechas import hoy_venezuela
from app.services.pdf import generar_pdf

# Documentos PDF: contienen datos clinicos, solo dra (igual que visitas,
# odontograma y periodontograma).
router = APIRouter(tags=["pdf"], dependencies=[Depends(requerir_dra)])


@router.get("/pacientes/{paciente_id}/pdf/prueba")
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


@router.get("/pdf/formulario-ingreso")
async def pdf_formulario_ingreso(
    session: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(get_current_usuario),
):
    """
    Formulario de ingreso EN BLANCO (Documento 4 de 5), para llenar a mano
    mientras la Dra. sigue en papel y transcribir despues 1 a 1 a la ficha
    digital. Standalone: no depende de ningun paciente. Solo lee el
    profesional del usuario, para el membrete.
    """
    profesional = await profesional_del_usuario(usuario, session)
    pdf = await generar_pdf(
        "formulario_ingreso.html",
        {"profesional": profesional, "antecedentes": ANTECEDENTES_FORMULARIO},
    )
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": 'inline; filename="formulario-ingreso.pdf"'},
    )
