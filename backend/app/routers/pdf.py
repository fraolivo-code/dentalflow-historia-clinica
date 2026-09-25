from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session, requerir_dra
from app.routers.pacientes import obtener_paciente_o_404
from app.services.pdf import generar_pdf

# Documentos PDF: contienen datos clinicos, solo dra (igual que visitas,
# odontograma y periodontograma).
router = APIRouter(tags=["pdf"], dependencies=[Depends(requerir_dra)])

# Venezuela no tiene horario de verano desde 2016: UTC-4 fijo. El contenedor
# corre en UTC, asi que la fecha "de hoy" se calcula con este offset.
HORA_VENEZUELA = timezone(timedelta(hours=-4))


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
            "fecha": datetime.now(HORA_VENEZUELA).strftime("%d/%m/%Y"),
        },
    )
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="prueba-{paciente.numero_historia}.pdf"'
        },
    )
