from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session
from app.enums import NUMEROS_DIENTE_VALIDOS
from app.models.odontograma import DienteAnatomia, OdontogramaHallazgo, OdontogramaLesionApical
from app.routers.pacientes import obtener_paciente_o_404
from app.schemas.odontograma import (
    DienteAnatomiaRead,
    OdontogramaHallazgoCreate,
    OdontogramaHallazgoRead,
    OdontogramaLesionApicalCreate,
    OdontogramaLesionApicalRead,
)
from app.services.odontograma_logic import aplicar_hallazgo, resolver_tipo_lesion_apical

router = APIRouter(tags=["odontograma"])


def _validar_numero_diente(numero_diente: int) -> None:
    if numero_diente not in NUMEROS_DIENTE_VALIDOS:
        raise HTTPException(400, f"{numero_diente} no es un numero de diente valido (FDI)")


@router.get("/dientes", response_model=list[DienteAnatomiaRead])
async def listar_catalogo_dientes(session: AsyncSession = Depends(get_session)):
    resultado = await session.execute(select(DienteAnatomia).order_by(DienteAnatomia.numero_diente))
    return resultado.scalars().all()


@router.get("/dientes/{numero_diente}", response_model=DienteAnatomiaRead)
async def obtener_anatomia_diente(numero_diente: int, session: AsyncSession = Depends(get_session)):
    _validar_numero_diente(numero_diente)
    anatomia = await session.get(DienteAnatomia, numero_diente)
    if anatomia is None:
        raise HTTPException(404, "Diente no encontrado en el catalogo")
    return anatomia


@router.get("/pacientes/{paciente_id}/odontograma", response_model=list[OdontogramaHallazgoRead])
async def obtener_odontograma_actual(
    paciente_id: UUID, session: AsyncSession = Depends(get_session)
):
    """Hallazgos actualmente activos de todo el odontograma del paciente (3.1)."""
    await obtener_paciente_o_404(paciente_id, session)
    resultado = await session.execute(
        select(OdontogramaHallazgo).where(
            OdontogramaHallazgo.paciente_id == paciente_id,
            OdontogramaHallazgo.activo.is_(True),
        )
    )
    return resultado.scalars().all()


@router.post(
    "/pacientes/{paciente_id}/dientes/{numero_diente}/hallazgos",
    response_model=OdontogramaHallazgoRead,
    status_code=201,
)
async def crear_hallazgo(
    paciente_id: UUID,
    numero_diente: int,
    datos: OdontogramaHallazgoCreate,
    session: AsyncSession = Depends(get_session),
):
    """Aplica un hallazgo respetando las reglas de exclusividad (3.3)."""
    if datos.numero_diente != numero_diente:
        raise HTTPException(400, "numero_diente del body no coincide con el de la URL")
    await obtener_paciente_o_404(paciente_id, session)
    return await aplicar_hallazgo(session, paciente_id, numero_diente, datos)


@router.get(
    "/pacientes/{paciente_id}/dientes/{numero_diente}/hallazgos",
    response_model=list[OdontogramaHallazgoRead],
)
async def listar_hallazgos_de_diente(
    paciente_id: UUID, numero_diente: int, session: AsyncSession = Depends(get_session)
):
    """Historico completo del diente, incluidos los hallazgos ya cerrados (activo=False)."""
    _validar_numero_diente(numero_diente)
    await obtener_paciente_o_404(paciente_id, session)
    resultado = await session.execute(
        select(OdontogramaHallazgo)
        .where(
            OdontogramaHallazgo.paciente_id == paciente_id,
            OdontogramaHallazgo.numero_diente == numero_diente,
        )
        .order_by(OdontogramaHallazgo.fecha)
    )
    return resultado.scalars().all()


@router.post(
    "/pacientes/{paciente_id}/dientes/{numero_diente}/lesion-apical",
    response_model=OdontogramaLesionApicalRead,
    status_code=201,
)
async def crear_lesion_apical(
    paciente_id: UUID,
    numero_diente: int,
    datos: OdontogramaLesionApicalCreate,
    session: AsyncSession = Depends(get_session),
):
    """
    Crea la lesion apical (1.3): valida la raiz contra diente_anatomia y
    calcula periapical/periimplantitis segun si el diente tiene implante activo.
    """
    if datos.numero_diente != numero_diente:
        raise HTTPException(400, "numero_diente del body no coincide con el de la URL")
    await obtener_paciente_o_404(paciente_id, session)
    tipo = await resolver_tipo_lesion_apical(session, paciente_id, numero_diente, datos.raiz)

    lesion = OdontogramaLesionApical(
        paciente_id=paciente_id,
        numero_diente=numero_diente,
        visita_id=datos.visita_id,
        raiz=datos.raiz,
        tipo=tipo,
        fecha=datos.fecha,
        creado_por=datos.creado_por,
    )
    session.add(lesion)
    await session.commit()
    await session.refresh(lesion)
    return lesion


@router.get(
    "/pacientes/{paciente_id}/dientes/{numero_diente}/lesion-apical",
    response_model=list[OdontogramaLesionApicalRead],
)
async def listar_lesiones_apicales_de_diente(
    paciente_id: UUID, numero_diente: int, session: AsyncSession = Depends(get_session)
):
    _validar_numero_diente(numero_diente)
    await obtener_paciente_o_404(paciente_id, session)
    resultado = await session.execute(
        select(OdontogramaLesionApical).where(
            OdontogramaLesionApical.paciente_id == paciente_id,
            OdontogramaLesionApical.numero_diente == numero_diente,
        )
    )
    return resultado.scalars().all()
