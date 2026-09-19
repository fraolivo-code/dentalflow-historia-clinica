from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session, requerir_dra
from app.models.common import ahora
from app.models.tratamiento import Tratamiento, TratamientoDiente
from app.routers.pacientes import obtener_paciente_o_404
from app.routers.profesionales_tratantes import obtener_profesional_tratante_o_404
from app.schemas.tratamiento import TratamientoCreate, TratamientoRead, TratamientoUpdate

router = APIRouter(tags=["tratamientos"], dependencies=[Depends(requerir_dra)])


async def _leer_tratamiento_con_dientes(session: AsyncSession, tratamiento: Tratamiento) -> Tratamiento:
    resultado = await session.execute(
        select(TratamientoDiente.numero_diente)
        .where(TratamientoDiente.tratamiento_id == tratamiento.id)
        .order_by(TratamientoDiente.numero_diente)
    )
    tratamiento.dientes = list(resultado.scalars().all())  # atributo dinamico, no mapeado
    return tratamiento


@router.post("/pacientes/{paciente_id}/tratamientos", response_model=TratamientoRead, status_code=201)
async def crear_tratamiento(
    paciente_id: UUID, datos: TratamientoCreate, session: AsyncSession = Depends(get_session)
):
    await obtener_paciente_o_404(paciente_id, session)
    await obtener_profesional_tratante_o_404(datos.profesional_tratante_id, session)

    tratamiento = Tratamiento(
        paciente_id=paciente_id,
        tipo=datos.tipo,
        estado=datos.estado,
        origen=datos.origen,
        origen_detalle=datos.origen_detalle,
        fecha_inicio=datos.fecha_inicio,
        fecha_fin=datos.fecha_fin,
        profesional_tratante_id=datos.profesional_tratante_id,
        notas_relevantes=datos.notas_relevantes,
        creado_por=datos.creado_por,
    )
    session.add(tratamiento)
    await session.flush()  # necesitamos tratamiento.id antes de crear los hijos

    for numero_diente in datos.dientes:
        session.add(
            TratamientoDiente(
                tratamiento_id=tratamiento.id,
                numero_diente=numero_diente,
                creado_por=datos.creado_por,
            )
        )

    await session.commit()
    await session.refresh(tratamiento)
    return await _leer_tratamiento_con_dientes(session, tratamiento)


@router.get("/pacientes/{paciente_id}/tratamientos", response_model=list[TratamientoRead])
async def listar_tratamientos_de_paciente(
    paciente_id: UUID, session: AsyncSession = Depends(get_session)
):
    resultado = await session.execute(
        select(Tratamiento).where(Tratamiento.paciente_id == paciente_id)
    )
    tratamientos = resultado.scalars().all()
    return [await _leer_tratamiento_con_dientes(session, t) for t in tratamientos]


@router.get("/tratamientos/{tratamiento_id}", response_model=TratamientoRead)
async def obtener_tratamiento(tratamiento_id: UUID, session: AsyncSession = Depends(get_session)):
    tratamiento = await session.get(Tratamiento, tratamiento_id)
    if tratamiento is None:
        raise HTTPException(404, "Tratamiento no encontrado")
    return await _leer_tratamiento_con_dientes(session, tratamiento)


@router.patch("/tratamientos/{tratamiento_id}", response_model=TratamientoRead)
async def actualizar_tratamiento(
    tratamiento_id: UUID, datos: TratamientoUpdate, session: AsyncSession = Depends(get_session)
):
    """Avance del ciclo de vida (indicado -> en_curso -> completado/suspendido)."""
    tratamiento = await session.get(Tratamiento, tratamiento_id)
    if tratamiento is None:
        raise HTTPException(404, "Tratamiento no encontrado")

    cambios = datos.model_dump(exclude={"actualizado_por"}, exclude_unset=True)
    for campo, valor in cambios.items():
        setattr(tratamiento, campo, valor)
    tratamiento.actualizado_en = ahora()
    tratamiento.actualizado_por = datos.actualizado_por

    await session.commit()
    await session.refresh(tratamiento)
    return await _leer_tratamiento_con_dientes(session, tratamiento)
