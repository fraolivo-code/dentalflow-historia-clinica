from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_usuario, get_session, requerir_dra
from app.models.bitacora_tratamiento import BitacoraDiente, BitacoraTratamiento
from app.models.tratamiento import Tratamiento
from app.models.usuario import Usuario
from app.routers.pacientes import obtener_paciente_o_404
from app.schemas.bitacora_tratamiento import BitacoraTratamientoCreate, BitacoraTratamientoRead
from app.schemas.odontograma import OdontogramaHallazgoCreate
from app.services.odontograma_logic import aplicar_hallazgo, buscar_duplicado_activo, orden_anatomico

router = APIRouter(tags=["bitacora"], dependencies=[Depends(requerir_dra)])


async def con_dientes(
    session: AsyncSession, entradas: list[BitacoraTratamiento]
) -> list[BitacoraTratamiento]:
    """
    Adjunta `dientes` (atributo dinamico, no mapeado) a cada entrada, en orden
    anatomico. Una entrada anterior a la migracion 0022 sin filas en
    bitacora_diente cae a su columna `numero_diente`.
    """
    if not entradas:
        return entradas
    filas = await session.execute(
        select(BitacoraDiente.bitacora_id, BitacoraDiente.numero_diente).where(
            BitacoraDiente.bitacora_id.in_([e.id for e in entradas])
        )
    )
    por_entrada: dict[UUID, list[int]] = {e.id: [] for e in entradas}
    for bitacora_id, numero in filas:
        por_entrada[bitacora_id].append(numero)
    for e in entradas:
        lista = por_entrada[e.id] or ([e.numero_diente] if e.numero_diente is not None else [])
        e.dientes = sorted(lista, key=orden_anatomico)
    return entradas


def _error_de_diente(error: HTTPException, numero_diente: int) -> HTTPException:
    """Mismo estado del error original, con el diente y la aclaracion de que no se guardo nada."""
    prefijo = f"No se guardó la entrada: el hallazgo del diente {numero_diente} no se pudo registrar. "
    detalle = error.detail
    if isinstance(detalle, dict):
        detalle = {**detalle, "mensaje": prefijo + str(detalle.get("mensaje", ""))}
    else:
        detalle = prefijo + str(detalle)
    return HTTPException(error.status_code, detalle)


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
    Crea la entrada de bitacora con sus dientes y, si hay dientes y
    tipo_hallazgo, el hallazgo del odontograma EN CADA DIENTE (seccion 7 de la
    especificacion de formularios), reutilizando las reglas de exclusividad de
    la Etapa 4 (aplicar_hallazgo).

    Todo en UNA transaccion (04/10/2026): si el hallazgo de cualquier diente
    falla (ej. 409 por puente activo), no se guarda nada y el error nombra el
    diente.

    Si un diente ya tiene ese hallazgo activo e identico (mismo diente + tipo +
    superficie), la entrada se guarda igual y a ese diente no se le crea un
    hallazgo duplicado, sin error: una sesion mas de un tratamiento
    multisesion no debe bloquearse (confirmado 23/09/2026).
    """
    await obtener_paciente_o_404(paciente_id, session)
    if datos.tratamiento_id is not None:
        tratamiento = await session.get(Tratamiento, datos.tratamiento_id)
        if tratamiento is None:
            raise HTTPException(404, "Tratamiento no encontrado")
        if tratamiento.paciente_id != paciente_id:
            raise HTTPException(422, "El tratamiento no pertenece a este paciente")

    dientes = datos.dientes_de_la_entrada()
    entrada = BitacoraTratamiento(
        paciente_id=paciente_id,
        visita_id=datos.visita_id,
        fecha=datos.fecha,
        responsable=usuario.id,
        descripcion=datos.descripcion,
        numero_diente=dientes[0] if dientes else None,
        tratamiento_id=datos.tratamiento_id,
        tipo_hallazgo=datos.tipo_hallazgo,
        superficie=datos.superficie,
        creado_por=usuario.id,
    )
    session.add(entrada)
    await session.flush()
    for numero in dientes:
        session.add(BitacoraDiente(bitacora_id=entrada.id, numero_diente=numero, creado_por=usuario.id))

    if datos.tipo_hallazgo is not None:
        for numero in dientes:
            if await buscar_duplicado_activo(
                session, paciente_id, numero, datos.tipo_hallazgo, datos.superficie
            ):
                continue
            try:
                await aplicar_hallazgo(
                    session,
                    paciente_id,
                    numero,
                    OdontogramaHallazgoCreate(
                        numero_diente=numero,
                        visita_id=datos.visita_id,
                        tipo_hallazgo=datos.tipo_hallazgo,
                        superficie=datos.superficie,
                        fecha=datos.fecha,
                        notas=None,
                        tratamiento_id=datos.tratamiento_id,
                    ),
                    usuario.id,
                    commit=False,
                )
            except HTTPException as error:
                await session.rollback()
                raise _error_de_diente(error, numero)

    await session.commit()
    await session.refresh(entrada)
    return (await con_dientes(session, [entrada]))[0]


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
    return await con_dientes(session, list(resultado.scalars().all()))


@router.get("/bitacora/{entrada_id}", response_model=BitacoraTratamientoRead)
async def obtener_entrada_bitacora(entrada_id: UUID, session: AsyncSession = Depends(get_session)):
    entrada = await session.get(BitacoraTratamiento, entrada_id)
    if entrada is None:
        raise HTTPException(404, "Entrada de bitacora no encontrada")
    return (await con_dientes(session, [entrada]))[0]
