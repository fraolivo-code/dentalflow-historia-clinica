from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import ROLES_ACCESO_TOTAL, get_current_usuario, get_session, requerir_acceso_total
from app.models.common import ahora
from app.models.paciente import Paciente
from app.models.paciente_cambio import PacienteCambio
from app.models.usuario import Usuario
from app.schemas.paciente import (
    NumeroHistoriaCorreccion,
    PacienteCambioRead,
    PacienteCreate,
    PacienteRead,
    PacienteUpdate,
)
from app.services import auditoria, correlativos, paciente_cambios

# Paciente basico: accesible para dra y asistente por igual (ambas necesitan
# poder ver/crear pacientes) — solo exige estar autenticado, sin rol especifico.
router = APIRouter(
    prefix="/pacientes", tags=["pacientes"], dependencies=[Depends(get_current_usuario)]
)


# Desde esta edad la cedula es obligatoria; antes, opcional (el sistema la pide al cumplirla).
EDAD_CEDULA_OBLIGATORIA = 12
# Datos de identidad que la asistente puede completar (no cambiar) si estan vacios.
CAMPOS_COMPLETABLES = frozenset({"cedula", "fecha_nacimiento"})


def _edad(nacimiento: date, hoy: date) -> int:
    return hoy.year - nacimiento.year - ((hoy.month, hoy.day) < (nacimiento.month, nacimiento.day))


def _validar_identificacion(cedula: str | None, nacimiento: date | None) -> None:
    if nacimiento is None:
        raise HTTPException(422, "La fecha de nacimiento es obligatoria.")
    hoy = date.today()
    if nacimiento > hoy:
        raise HTTPException(422, "La fecha de nacimiento no puede ser futura.")
    if cedula is None and _edad(nacimiento, hoy) >= EDAD_CEDULA_OBLIGATORIA:
        raise HTTPException(422, f"La cédula es obligatoria desde los {EDAD_CEDULA_OBLIGATORIA} años.")


async def _verificar_cedula_libre(
    session: AsyncSession, cedula: str | None, excluir_id: UUID | None = None
) -> None:
    if cedula is None:
        return
    consulta = select(Paciente.numero_historia, Paciente.nombre_completo).where(
        Paciente.cedula == cedula
    )
    if excluir_id is not None:
        consulta = consulta.where(Paciente.id != excluir_id)
    existente = (await session.execute(consulta)).first()
    if existente is not None:
        raise HTTPException(
            409,
            f"Ya existe un paciente con la cédula {cedula}: historia "
            f"{existente.numero_historia}, {existente.nombre_completo}. Ábralo desde Pacientes.",
        )


@router.post("", response_model=PacienteRead, status_code=201)
async def crear_paciente(
    datos: PacienteCreate,
    session: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(get_current_usuario),
):
    _validar_identificacion(datos.cedula, datos.fecha_nacimiento)
    await _verificar_cedula_libre(session, datos.cedula)
    ancho = await correlativos.ancho_configurado(session)
    if datos.numero_historia is None:
        try:
            numero_historia = await correlativos.generar_numero_historia(session)
        except correlativos.NumeracionAgotada as error:
            raise HTTPException(409, str(error))
    else:
        # Fijar el numero a mano (historia vieja en papel): solo acceso total.
        if usuario.rol not in ROLES_ACCESO_TOTAL:
            raise HTTPException(403, "No tiene permiso para fijar el número de historia.")
        try:
            numero_historia = correlativos.normalizar_manual(datos.numero_historia, ancho)
        except correlativos.NumeroInvalido as error:
            raise HTTPException(422, str(error))
        if int(numero_historia) in await correlativos.numeros_en_uso(session):
            raise HTTPException(409, f"Ya existe una historia con el número {numero_historia}.")
    paciente = Paciente(
        **datos.model_dump(exclude={"numero_historia"}),
        numero_historia=numero_historia,
        creado_por=usuario.id,
    )
    session.add(paciente)
    try:
        await session.commit()
    except IntegrityError:
        # Carrera con otra alta que tomo el mismo numero o la misma cedula.
        await session.rollback()
        await _verificar_cedula_libre(session, datos.cedula)
        raise HTTPException(409, f"Ya existe una historia con el número {numero_historia}.")
    await session.refresh(paciente)
    return paciente


@router.get("", response_model=list[PacienteRead])
async def listar_pacientes(q: str | None = None, session: AsyncSession = Depends(get_session)):
    """
    q busca por nombre_completo (parcial, sin distinguir mayusculas/acentos
    via la extension unaccent de Postgres — migracion 0005) o por
    numero_historia (parcial). Regla de negocio: seccion 4 de
    especificacion-tecnica-formularios-fase2.md.
    """
    query = select(Paciente)
    if q:
        patron = f"%{q}%"
        query = query.where(
            or_(
                func.unaccent(Paciente.nombre_completo).ilike(func.unaccent(patron)),
                Paciente.numero_historia.ilike(patron),
            )
        )
    resultado = await session.execute(query.order_by(Paciente.nombre_completo))
    return resultado.scalars().all()


@router.get("/{paciente_id}", response_model=PacienteRead)
async def obtener_paciente(paciente_id: UUID, session: AsyncSession = Depends(get_session)):
    paciente = await session.get(Paciente, paciente_id)
    if paciente is None:
        raise HTTPException(404, "Paciente no encontrado")
    return paciente


@router.patch("/{paciente_id}", response_model=PacienteRead)
async def actualizar_paciente(
    paciente_id: UUID,
    datos: PacienteUpdate,
    session: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(get_current_usuario),
):
    """
    Correccion parcial de los datos del paciente (04/10/2026). Autorizacion por
    campo: el acceso total corrige todo; la asistente, solo los datos de
    contacto (cualquier otro campo, o uno sin clasificar, -> 403 y no se aplica
    nada). Cada campo que realmente cambia queda en paciente_cambio.
    numero_historia no pasa por aqui: tiene su propio endpoint.
    """
    cambios = datos.model_dump(exclude_unset=True)
    total = usuario.rol in ROLES_ACCESO_TOTAL
    if not total and not all(
        c in paciente_cambios.CAMPOS_CONTACTO | CAMPOS_COMPLETABLES for c in cambios
    ):
        raise HTTPException(403, "Solo puede corregir los datos de contacto del paciente.")
    paciente = await obtener_paciente_o_404(paciente_id, session)
    if not total and any(
        getattr(paciente, c) is not None for c in CAMPOS_COMPLETABLES if c in cambios
    ):
        raise HTTPException(403, "Solo la Dra. puede cambiar una cédula o fecha de nacimiento ya registrada.")
    if CAMPOS_COMPLETABLES & cambios.keys():
        cedula = cambios["cedula"] if "cedula" in cambios else paciente.cedula
        nacimiento = (
            cambios["fecha_nacimiento"] if "fecha_nacimiento" in cambios else paciente.fecha_nacimiento
        )
        _validar_identificacion(cedula, nacimiento)
        if "cedula" in cambios:
            await _verificar_cedula_libre(session, cedula, excluir_id=paciente.id)
    realizados = []
    for campo, valor in cambios.items():
        anterior = getattr(paciente, campo)
        if anterior != valor:
            realizados.append((campo, anterior, valor))
            setattr(paciente, campo, valor)
    if realizados:
        paciente.actualizado_en = ahora()
        paciente.actualizado_por = usuario.id
        paciente_cambios.registrar(session, paciente.id, usuario.id, realizados)
        await session.commit()
        await session.refresh(paciente)
    return paciente


@router.post("/{paciente_id}/numero-historia", response_model=PacienteRead)
async def corregir_numero_historia(
    paciente_id: UUID,
    datos: NumeroHistoriaCorreccion,
    session: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(requerir_acceso_total),
):
    """Correccion controlada del numero visible (el paciente se identifica por su UUID)."""
    if datos.confirmo is not True:
        raise HTTPException(422, "Debe confirmar la corrección del número.")
    paciente = await obtener_paciente_o_404(paciente_id, session)
    try:
        nuevo = correlativos.normalizar_manual(
            datos.numero_nuevo, await correlativos.ancho_configurado(session)
        )
    except correlativos.NumeroInvalido as error:
        raise HTTPException(422, str(error))
    actual = paciente.numero_historia
    if nuevo == actual:
        raise HTTPException(422, "El número nuevo es igual al actual.")
    # Mismo valor con otro ancho (0433 -> 000433) es solo reformatear: no choca consigo mismo.
    reformateo = actual.isdecimal() and int(nuevo) == int(actual)
    if not reformateo and int(nuevo) in await correlativos.numeros_en_uso(session):
        raise HTTPException(409, f"Ya existe una historia con el número {nuevo}.")
    paciente.numero_historia = nuevo
    paciente.actualizado_en = ahora()
    paciente.actualizado_por = usuario.id
    paciente_cambios.registrar(
        session, paciente.id, usuario.id, [("numero_historia", actual, nuevo)]
    )
    auditoria.registrar(
        session, "numero_historia_corregido", actor_id=usuario.id, detalle=f"{actual} -> {nuevo}"
    )
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(409, f"Ya existe una historia con el número {nuevo}.")
    await session.refresh(paciente)
    return paciente


@router.get(
    "/{paciente_id}/cambios",
    response_model=list[PacienteCambioRead],
    dependencies=[Depends(requerir_acceso_total)],
)
async def listar_cambios(paciente_id: UUID, session: AsyncSession = Depends(get_session)):
    """Historial de correcciones, del mas reciente al mas antiguo."""
    await obtener_paciente_o_404(paciente_id, session)
    filas = await session.execute(
        select(PacienteCambio, Usuario.nombre)
        .outerjoin(Usuario, Usuario.id == PacienteCambio.actor_id)
        .where(PacienteCambio.paciente_id == paciente_id)
        .order_by(PacienteCambio.fecha.desc(), PacienteCambio.campo)
    )
    return [
        PacienteCambioRead(
            id=c.id,
            fecha=c.fecha,
            actor_nombre=nombre,
            campo=c.campo,
            etiqueta=paciente_cambios.etiqueta(c.campo),
            valor_anterior=c.valor_anterior,
            valor_nuevo=c.valor_nuevo,
        )
        for c, nombre in filas
    ]


async def obtener_paciente_o_404(paciente_id: UUID, session: AsyncSession) -> Paciente:
    """Usado por otros routers (visitas, odontograma, etc.) que cuelgan de /pacientes/{id}."""
    paciente = await session.get(Paciente, paciente_id)
    if paciente is None:
        raise HTTPException(404, "Paciente no encontrado")
    return paciente
