from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_usuario, get_session, requerir_dra
from app.models.bitacora_tratamiento import BitacoraTratamiento
from app.models.tratamiento import Tratamiento
from app.models.usuario import Usuario
from app.routers.pacientes import obtener_paciente_o_404
from app.schemas.bitacora_tratamiento import BitacoraTratamientoCreate, BitacoraTratamientoRead
from app.schemas.odontograma import OdontogramaHallazgoCreate
from app.services.odontograma_logic import aplicar_hallazgo, buscar_duplicado_activo

router = APIRouter(tags=["bitacora"], dependencies=[Depends(requerir_dra)])


@router.post(
    "/pacientes/{paciente_id}/bitacora", response_model=BitacoraTratamientoRead, status_code=201
)
async def crear_entrada_bitacora(
    paciente_id: UUID,
    datos: BitacoraTratamientoCreate,
    session: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(get_current_usuario),
):
    """
    Crea la entrada de bitacora y, si trae numero_diente + tipo_hallazgo,
    crea automaticamente la fila correspondiente en odontograma_hallazgo
    (seccion 7 de la especificacion de formularios) reutilizando las mismas
    reglas de exclusividad de la Etapa 4 (aplicar_hallazgo).

    Si el hallazgo ya existe activo e identico (mismo diente + tipo +
    superficie), la entrada se guarda igual pero no se crea un hallazgo
    duplicado, sin error: una sesion mas de un tratamiento multisesion no
    debe bloquearse (confirmado 23/09/2026).
    """
    await obtener_paciente_o_404(paciente_id, session)
    if datos.tratamiento_id is not None:
        tratamiento = await session.get(Tratamiento, datos.tratamiento_id)
        if tratamiento is None:
            raise HTTPException(404, "Tratamiento no encontrado")

    entrada = BitacoraTratamiento(
        paciente_id=paciente_id,
        visita_id=datos.visita_id,
        fecha=datos.fecha,
        responsable=usuario.id,
        descripcion=datos.descripcion,
        numero_diente=datos.numero_diente,
        tratamiento_id=datos.tratamiento_id,
        tipo_hallazgo=datos.tipo_hallazgo,
        superficie=datos.superficie,
        creado_por=usuario.id,
    )
    session.add(entrada)
    await session.commit()
    await session.refresh(entrada)

    if (
        datos.numero_diente is not None
        and datos.tipo_hallazgo is not None
        and await buscar_duplicado_activo(
            session, paciente_id, datos.numero_diente, datos.tipo_hallazgo, datos.superficie
        )
        is None
    ):
        await aplicar_hallazgo(
            session,
            paciente_id,
            datos.numero_diente,
            OdontogramaHallazgoCreate(
                numero_diente=datos.numero_diente,
                visita_id=datos.visita_id,
                tipo_hallazgo=datos.tipo_hallazgo,
                superficie=datos.superficie,
                fecha=datos.fecha,
                notas=None,
                tratamiento_id=datos.tratamiento_id,
            ),
            usuario.id,
        )

    return entrada


@router.get("/pacientes/{paciente_id}/bitacora", response_model=list[BitacoraTratamientoRead])
async def listar_bitacora_de_paciente(
    paciente_id: UUID, session: AsyncSession = Depends(get_session)
):
    """Mas reciente primero (seccion 9: "orden de cualquier historial")."""
    resultado = await session.execute(
        select(BitacoraTratamiento)
        .where(BitacoraTratamiento.paciente_id == paciente_id)
        .order_by(BitacoraTratamiento.fecha.desc())
    )
    return resultado.scalars().all()


@router.get("/bitacora/{entrada_id}", response_model=BitacoraTratamientoRead)
async def obtener_entrada_bitacora(entrada_id: UUID, session: AsyncSession = Depends(get_session)):
    entrada = await session.get(BitacoraTratamiento, entrada_id)
    if entrada is None:
        raise HTTPException(404, "Entrada de bitacora no encontrada")
    return entrada
