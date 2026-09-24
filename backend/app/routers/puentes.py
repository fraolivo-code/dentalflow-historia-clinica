from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_usuario, get_session, requerir_dra
from app.models.common import ahora
from app.models.odontograma import PuenteFijo, PuenteFijoDiente
from app.models.usuario import Usuario
from app.routers.pacientes import obtener_paciente_o_404
from app.schemas.odontograma import PuenteFijoCreate, PuenteFijoRead, PuenteFijoResolver
from app.services.odontograma_logic import (
    orden_anatomico,
    resolver_condicion_individual_puente,
    validar_contiguidad_puente,
    validar_hallazgos_bloqueantes_puente,
    validar_puente_sin_solapamiento,
)

# Parte del dominio odontograma (clinico) -> dra solamente.
router = APIRouter(tags=["puentes"], dependencies=[Depends(requerir_dra)])


async def _leer_puente_con_dientes(session: AsyncSession, puente: PuenteFijo) -> PuenteFijo:
    """Adjunta `dientes` (no es una relacion ORM) en orden anatomico real (3.2)."""
    resultado = await session.execute(
        select(PuenteFijoDiente).where(PuenteFijoDiente.puente_id == puente.id)
    )
    dientes = sorted(resultado.scalars().all(), key=lambda d: orden_anatomico(d.numero_diente))
    puente.dientes = dientes  # atributo dinamico, no mapeado por el ORM
    return puente


@router.post("/pacientes/{paciente_id}/puentes", response_model=PuenteFijoRead, status_code=201)
async def crear_puente(
    paciente_id: UUID,
    datos: PuenteFijoCreate,
    session: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(get_current_usuario),
):
    """
    Crea el puente completo en un solo pedido. La regla rol <-> condicion se
    valida en el schema (422); aqui: contiguidad (400), un diente en otro
    puente activo (409) y hallazgos de estado/endo que lo bloquean (409).
    """
    await obtener_paciente_o_404(paciente_id, session)
    condiciones = [resolver_condicion_individual_puente(d.condicion_individual) for d in datos.dientes]
    numeros = [d.numero_diente for d in datos.dientes]
    validar_contiguidad_puente(numeros)
    await validar_puente_sin_solapamiento(session, paciente_id, numeros)
    await validar_hallazgos_bloqueantes_puente(session, paciente_id, datos.dientes)

    puente = PuenteFijo(
        paciente_id=paciente_id,
        visita_id=datos.visita_id,
        estado_general=datos.estado_general,
        fecha=datos.fecha,
        creado_por=usuario.id,
    )
    session.add(puente)
    await session.flush()  # necesitamos puente.id antes de crear los hijos

    for diente, condicion in zip(datos.dientes, condiciones):
        session.add(
            PuenteFijoDiente(
                puente_id=puente.id,
                numero_diente=diente.numero_diente,
                rol=diente.rol,
                condicion_individual=condicion,
                creado_por=usuario.id,
            )
        )

    await session.commit()
    await session.refresh(puente)
    return await _leer_puente_con_dientes(session, puente)


@router.get("/pacientes/{paciente_id}/puentes", response_model=list[PuenteFijoRead])
async def listar_puentes_de_paciente(
    paciente_id: UUID, session: AsyncSession = Depends(get_session)
):
    """Puentes activos (no resueltos) del paciente, como GET .../odontograma (24/09/2026)."""
    await obtener_paciente_o_404(paciente_id, session)
    resultado = await session.execute(
        select(PuenteFijo)
        .where(PuenteFijo.paciente_id == paciente_id, PuenteFijo.resuelto.is_(False))
        .order_by(PuenteFijo.fecha)
    )
    puentes = resultado.scalars().all()
    return [await _leer_puente_con_dientes(session, p) for p in puentes]


@router.patch(
    "/pacientes/{paciente_id}/puentes/{puente_id}/resolver", response_model=PuenteFijoRead
)
async def resolver_puente(
    paciente_id: UUID,
    puente_id: UUID,
    datos: PuenteFijoResolver,
    session: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(get_current_usuario),
):
    """
    Cierre de un puente activo (24/09/2026): mismo patron que
    PATCH .../hallazgos/{id}/resolver — resuelto=True con fecha, sin borrar.
    Sus dientes quedan libres para hallazgos de estado/endo o para otro puente.
    """
    puente = await session.get(PuenteFijo, puente_id)
    # Un puente de otro paciente responde igual que uno inexistente.
    if puente is None or puente.paciente_id != paciente_id:
        raise HTTPException(404, "Puente no encontrado")
    if puente.resuelto:
        raise HTTPException(409, "El puente ya estaba resuelto")
    if datos.fecha < puente.fecha:
        raise HTTPException(
            422, "La fecha de resolucion no puede ser anterior a la fecha del puente"
        )

    puente.resuelto = True
    puente.resuelto_fecha = datos.fecha
    puente.actualizado_en = ahora()
    puente.actualizado_por = usuario.id
    await session.commit()
    await session.refresh(puente)
    return await _leer_puente_con_dientes(session, puente)


@router.get("/puentes/{puente_id}", response_model=PuenteFijoRead)
async def obtener_puente(puente_id: UUID, session: AsyncSession = Depends(get_session)):
    puente = await session.get(PuenteFijo, puente_id)
    if puente is None:
        raise HTTPException(404, "Puente no encontrado")
    return await _leer_puente_con_dientes(session, puente)
