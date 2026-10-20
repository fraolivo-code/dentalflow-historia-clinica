from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_usuario, get_session, requerir_dra
from app.enums import NUMEROS_DIENTE_VALIDOS
from app.models.common import ahora
from app.models.odontograma import (
    DienteAnatomia,
    OdontogramaCondicionGeneral,
    OdontogramaHallazgo,
    OdontogramaLesionApical,
)
from app.models.visita import Visita
from app.models.usuario import Usuario
from app.routers.pacientes import obtener_paciente_o_404
from app.schemas.odontograma import (
    CondicionGeneralCreate,
    CondicionGeneralRead,
    CondicionGeneralResolver,
    HallazgosLoteCreate,
    TratamientoRealizadoLoteCreate,
    DienteAnatomiaRead,
    OdontogramaHallazgoCreate,
    OdontogramaHallazgoRead,
    OdontogramaHallazgoResolver,
    OdontogramaLesionApicalCreate,
    OdontogramaLesionApicalRead,
    OdontogramaLesionApicalResolver,
    TratamientoRealizadoCreate,
    TratamientoRealizadoRead,
)
from app.services import tratamiento_realizado
from app.services.odontograma_logic import (
    aplicar_hallazgo,
    buscar_duplicado_activo,
    buscar_lesion_duplicada_activa,
    orden_anatomico,
    resolver_tipo_lesion_apical,
)

router = APIRouter(tags=["odontograma"], dependencies=[Depends(requerir_dra)])


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
    paciente_id: UUID,
    al: date | None = None,
    session: AsyncSession = Depends(get_session),
):
    """
    Hallazgos actualmente activos (no resueltos) del odontograma del paciente (3.1).
    Con `al` (fecha de una evaluacion o reevaluacion), el odontograma tal como estaba ese dia: lo marcado
    hasta esa fecha que todavia no estaba resuelto ese dia. Nada se guarda aparte: sale de las fechas
    de cada hallazgo (marcado y resuelto).
    """
    await obtener_paciente_o_404(paciente_id, session)
    condiciones = [OdontogramaHallazgo.paciente_id == paciente_id]
    if al is None:
        condiciones.append(OdontogramaHallazgo.resuelto.is_(False))
    else:
        condiciones += [
            OdontogramaHallazgo.fecha <= al,
            or_(OdontogramaHallazgo.resuelto.is_(False), OdontogramaHallazgo.resuelto_fecha > al),
        ]
    resultado = await session.execute(select(OdontogramaHallazgo).where(*condiciones))
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
    usuario: Usuario = Depends(get_current_usuario),
):
    """Aplica un hallazgo respetando las reglas de exclusividad (3.3)."""
    if datos.numero_diente != numero_diente:
        raise HTTPException(400, "numero_diente del body no coincide con el de la URL")
    await obtener_paciente_o_404(paciente_id, session)
    return await aplicar_hallazgo(session, paciente_id, numero_diente, datos, usuario.id)


@router.post("/pacientes/{paciente_id}/hallazgos-lote", status_code=201)
async def crear_hallazgos_en_lote(
    paciente_id: UUID,
    datos: HallazgosLoteCreate,
    session: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(get_current_usuario),
):
    """
    El mismo hallazgo en varios dientes (y superficies) en UNA transaccion: si algun diente falla
    (puente activo, hallazgo que no aplica en un deciduo...) no se guarda nada y el error nombra el
    diente. Un hallazgo identico y ya activo se omite sin error. Respeta las reglas de exclusividad.
    """
    await obtener_paciente_o_404(paciente_id, session)
    creados, omitidos = 0, []
    for numero in sorted(datos.dientes, key=orden_anatomico):
        for superficie in datos.superficies or [None]:
            if await buscar_duplicado_activo(session, paciente_id, numero, datos.tipo_hallazgo, superficie):
                omitidos.append(f"{numero}{f' ({superficie.value})' if superficie else ''}")
                continue
            try:
                await aplicar_hallazgo(
                    session,
                    paciente_id,
                    numero,
                    OdontogramaHallazgoCreate(
                        numero_diente=numero, visita_id=datos.visita_id, tipo_hallazgo=datos.tipo_hallazgo,
                        superficie=superficie, fecha=datos.fecha,
                    ),
                    usuario.id,
                    commit=False,
                )
            except HTTPException as error:
                await session.rollback()
                detalle = error.detail["mensaje"] if isinstance(error.detail, dict) else error.detail
                raise HTTPException(error.status_code, f"No se guardó nada: el diente {numero} falló. {detalle}")
            creados += 1
    await session.commit()
    return {"creados": creados, "omitidos": omitidos}


@router.post("/pacientes/{paciente_id}/tratamientos-realizados-lote", status_code=201)
async def registrar_tratamientos_realizados_en_lote(
    paciente_id: UUID,
    datos: TratamientoRealizadoLoteCreate,
    session: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(get_current_usuario),
):
    """
    Varios «Tratamiento realizado» de una misma fecha (y visita) en UNA transaccion: si alguno falla no se
    guarda ninguno y el error nombra el diente. Cada uno hace lo mismo que el registro por diente.
    """
    await obtener_paciente_o_404(paciente_id, session)
    try:
        for item in datos.items:
            await tratamiento_realizado.registrar(
                session,
                paciente_id,
                item.numero_diente,
                tratamiento=item.tratamiento,
                fecha=datos.fecha,
                superficies=item.superficies,
                resultado=item.resultado,
                cierra_ids=item.cierra_ids,
                descripcion=item.descripcion,
                visita_id=datos.visita_id,
                tratamiento_id=None,
                usuario_id=usuario.id,
                commit=False,
            )
    except HTTPException as error:
        await session.rollback()
        detalle = error.detail["mensaje"] if isinstance(error.detail, dict) else error.detail
        raise HTTPException(error.status_code, f"No se guardó nada: el diente {item.numero_diente} falló. {detalle}")
    await session.commit()
    return {"registrados": len(datos.items)}


@router.get("/tratamientos-realizados")
async def reglas_de_tratamientos_realizados():
    """Catalogo de la accion «Tratamiento realizado»: que abre y que cierra cada uno."""
    return tratamiento_realizado.catalogo()


@router.post(
    "/pacientes/{paciente_id}/dientes/{numero_diente}/tratamiento-realizado",
    response_model=TratamientoRealizadoRead,
    status_code=201,
)
async def registrar_tratamiento_realizado(
    paciente_id: UUID,
    numero_diente: int,
    datos: TratamientoRealizadoCreate,
    session: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(get_current_usuario),
):
    """
    Tratamiento terminado en un diente (15/10/2026): en una sola transaccion cierra los
    hallazgos «antes» y abre los «despues» con la fecha dada, y deja una entrada en la
    bitacora. Reglas: services/tratamiento_realizado.py.
    """
    if datos.numero_diente != numero_diente:
        raise HTTPException(400, "numero_diente del body no coincide con el de la URL")
    await obtener_paciente_o_404(paciente_id, session)
    cerrados, abiertos, entrada = await tratamiento_realizado.registrar(
        session,
        paciente_id,
        numero_diente,
        tratamiento=datos.tratamiento,
        fecha=datos.fecha,
        superficies=datos.superficies,
        resultado=datos.resultado,
        cierra_ids=datos.cierra_ids,
        descripcion=datos.descripcion,
        visita_id=datos.visita_id,
        tratamiento_id=datos.tratamiento_id,
        usuario_id=usuario.id,
    )
    return TratamientoRealizadoRead(
        cerrados=[OdontogramaHallazgoRead.model_validate(h) for h in cerrados],
        abiertos=[OdontogramaHallazgoRead.model_validate(h) for h in abiertos],
        bitacora_id=entrada.id,
    )


@router.patch(
    "/pacientes/{paciente_id}/hallazgos/{hallazgo_id}/resolver",
    response_model=OdontogramaHallazgoRead,
)
async def resolver_hallazgo(
    paciente_id: UUID,
    hallazgo_id: UUID,
    datos: OdontogramaHallazgoResolver,
    session: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(get_current_usuario),
):
    """
    Cierre manual de un hallazgo activo (23/09/2026): resuelto=True con
    fecha, sin borrar el historico. resuelto_por_hallazgo_id queda en NULL,
    que es lo que distingue un cierre manual de un reemplazo por exclusividad.
    """
    hallazgo = await session.get(OdontogramaHallazgo, hallazgo_id)
    # Un hallazgo de otro paciente responde igual que uno inexistente.
    if hallazgo is None or hallazgo.paciente_id != paciente_id:
        raise HTTPException(404, "Hallazgo no encontrado")
    if hallazgo.resuelto:
        raise HTTPException(409, "El hallazgo ya estaba resuelto")
    if datos.fecha < hallazgo.fecha:
        raise HTTPException(
            422, "La fecha de resolucion no puede ser anterior a la fecha del hallazgo"
        )

    hallazgo.resuelto = True
    hallazgo.resuelto_fecha = datos.fecha
    hallazgo.actualizado_en = ahora()
    hallazgo.actualizado_por = usuario.id
    await session.commit()
    await session.refresh(hallazgo)
    return hallazgo


@router.get(
    "/pacientes/{paciente_id}/dientes/{numero_diente}/hallazgos",
    response_model=list[OdontogramaHallazgoRead],
)
async def listar_hallazgos_de_diente(
    paciente_id: UUID, numero_diente: int, session: AsyncSession = Depends(get_session)
):
    """Historico completo del diente, incluidos los hallazgos ya cerrados (resuelto=True)."""
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
    usuario: Usuario = Depends(get_current_usuario),
):
    """
    Crea la lesion apical (1.3): valida la raiz contra diente_anatomia y
    calcula periapical/periimplantitis segun si el diente tiene implante activo.
    """
    if datos.numero_diente != numero_diente:
        raise HTTPException(400, "numero_diente del body no coincide con el de la URL")
    await obtener_paciente_o_404(paciente_id, session)
    tipo = await resolver_tipo_lesion_apical(session, paciente_id, numero_diente, datos.raiz)

    duplicada = await buscar_lesion_duplicada_activa(
        session, paciente_id, numero_diente, datos.raiz
    )
    if duplicada is not None:
        raise HTTPException(
            409,
            detail={
                "mensaje": (
                    f"El diente {numero_diente} ya tiene una lesion activa en la raiz {datos.raiz}"
                ),
                "lesion_existente_id": str(duplicada.id),
            },
        )

    lesion = OdontogramaLesionApical(
        paciente_id=paciente_id,
        numero_diente=numero_diente,
        visita_id=datos.visita_id,
        raiz=datos.raiz,
        tipo=tipo,
        fecha=datos.fecha,
        resuelto=False,
        creado_por=usuario.id,
    )
    session.add(lesion)
    await session.commit()
    await session.refresh(lesion)
    return lesion


@router.get(
    "/pacientes/{paciente_id}/lesiones-apicales",
    response_model=list[OdontogramaLesionApicalRead],
)
async def listar_lesiones_apicales_activas(
    paciente_id: UUID, session: AsyncSession = Depends(get_session)
):
    """Lesiones apicales activas de todos los dientes, en un solo pedido (23/09/2026)."""
    await obtener_paciente_o_404(paciente_id, session)
    resultado = await session.execute(
        select(OdontogramaLesionApical).where(
            OdontogramaLesionApical.paciente_id == paciente_id,
            OdontogramaLesionApical.resuelto.is_(False),
        )
    )
    return resultado.scalars().all()


@router.patch(
    "/pacientes/{paciente_id}/lesiones-apicales/{lesion_id}/resolver",
    response_model=OdontogramaLesionApicalRead,
)
async def resolver_lesion_apical(
    paciente_id: UUID,
    lesion_id: UUID,
    datos: OdontogramaLesionApicalResolver,
    session: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(get_current_usuario),
):
    """
    Cierre manual de una lesion apical activa (23/09/2026): mismo patron que
    PATCH .../hallazgos/{id}/resolver — resuelto=True con fecha, sin borrar.
    """
    lesion = await session.get(OdontogramaLesionApical, lesion_id)
    # Una lesion de otro paciente responde igual que una inexistente.
    if lesion is None or lesion.paciente_id != paciente_id:
        raise HTTPException(404, "Lesion apical no encontrada")
    if lesion.resuelto:
        raise HTTPException(409, "La lesion apical ya estaba resuelta")
    if datos.fecha < lesion.fecha:
        raise HTTPException(
            422, "La fecha de resolucion no puede ser anterior a la fecha de la lesion"
        )

    lesion.resuelto = True
    lesion.resuelto_fecha = datos.fecha
    lesion.actualizado_en = ahora()
    lesion.actualizado_por = usuario.id
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


# --- Condiciones de toda la boca (gingivitis), 19/10/2026 ----------------------------------------------------

@router.get("/pacientes/{paciente_id}/condiciones-generales", response_model=list[CondicionGeneralRead])
async def listar_condiciones_generales(
    paciente_id: UUID, al: date | None = None, session: AsyncSession = Depends(get_session)
):
    """Las vigentes; con `al`, las que estaban marcadas ese dia (igual que el odontograma «al dia»)."""
    await obtener_paciente_o_404(paciente_id, session)
    condiciones = [OdontogramaCondicionGeneral.paciente_id == paciente_id]
    if al is None:
        condiciones.append(OdontogramaCondicionGeneral.resuelto.is_(False))
    else:
        condiciones += [
            OdontogramaCondicionGeneral.fecha <= al,
            or_(OdontogramaCondicionGeneral.resuelto.is_(False), OdontogramaCondicionGeneral.resuelto_fecha > al),
        ]
    filas = await session.execute(select(OdontogramaCondicionGeneral).where(*condiciones))
    return filas.scalars().all()


@router.post(
    "/pacientes/{paciente_id}/condiciones-generales", response_model=CondicionGeneralRead, status_code=201
)
async def crear_condicion_general(
    paciente_id: UUID,
    datos: CondicionGeneralCreate,
    session: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(get_current_usuario),
):
    await obtener_paciente_o_404(paciente_id, session)
    if datos.visita_id is not None:
        visita = await session.get(Visita, datos.visita_id)
        if visita is None or visita.paciente_id != paciente_id:
            raise HTTPException(422, "La visita no existe o no es de este paciente.")
    ya_marcada = await session.execute(
        select(OdontogramaCondicionGeneral.id).where(
            OdontogramaCondicionGeneral.paciente_id == paciente_id,
            OdontogramaCondicionGeneral.tipo == datos.tipo,
            OdontogramaCondicionGeneral.resuelto.is_(False),
        )
    )
    if ya_marcada.first() is not None:
        raise HTTPException(409, f"{datos.tipo.value} ya esta marcada para este paciente")
    condicion = OdontogramaCondicionGeneral(paciente_id=paciente_id, **datos.model_dump(), creado_por=usuario.id)
    session.add(condicion)
    await session.commit()
    await session.refresh(condicion)
    return condicion


@router.patch(
    "/pacientes/{paciente_id}/condiciones-generales/{condicion_id}/resolver",
    response_model=CondicionGeneralRead,
)
async def resolver_condicion_general(
    paciente_id: UUID,
    condicion_id: UUID,
    datos: CondicionGeneralResolver,
    session: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(get_current_usuario),
):
    """Cierre manual (resuelto=True con fecha, sin borrar el historico)."""
    condicion = await session.get(OdontogramaCondicionGeneral, condicion_id)
    if condicion is None or condicion.paciente_id != paciente_id:
        raise HTTPException(404, "Condicion no encontrada")
    if condicion.resuelto:
        raise HTTPException(409, "La condicion ya estaba resuelta")
    if datos.fecha < condicion.fecha:
        raise HTTPException(422, "La fecha de resolucion no puede ser anterior a la fecha de la condicion")
    condicion.resuelto = True
    condicion.resuelto_fecha = datos.fecha
    condicion.actualizado_en = ahora()
    condicion.actualizado_por = usuario.id
    await session.commit()
    await session.refresh(condicion)
    return condicion
