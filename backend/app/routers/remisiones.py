# app/routers/remisiones.py — Lo que hace la Dra. con los especialistas (19/10/2026): remitir, retirar el acceso,
# ver y corregir lo que escribieron, y ver quien miro cada paciente. Solo dra.
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_usuario, get_session, requerir_dra
from app.enums import RolUsuario
from app.models.common import ahora
from app.models.profesional_tratante import ProfesionalTratante
from app.models.remision import AccesoPaciente, AtencionDiente, AtencionEspecialista, Remision, RemisionDiente
from app.models.usuario import Usuario
from app.routers.pacientes import obtener_paciente_o_404
from app.schemas.remision import (
    AccesoRead,
    AtencionRead,
    AtencionUpdate,
    EspecialistaRead,
    PinFijar,
    RemisionCreate,
    RemisionRead,
)
from app.security import hash_password, verificar_password
from app.services import especialista as svc
from app.services.correo import enviar_aviso_remision

router = APIRouter(tags=["remisiones"], dependencies=[Depends(requerir_dra)])


async def _remisiones_leidas(session: AsyncSession, remisiones: list[Remision]) -> list[RemisionRead]:
    dientes = await svc.dientes_por_remision(session, [r.id for r in remisiones])
    nombres = {
        u.id: u.nombre
        for u in (await session.execute(select(Usuario).where(Usuario.id.in_([r.especialista_id for r in remisiones])))).scalars()
    } if remisiones else {}
    return [
        RemisionRead.model_validate(r).model_copy(
            update={"dientes": dientes.get(r.id, []), "especialista_nombre": nombres.get(r.especialista_id)}
        )
        for r in remisiones
    ]


@router.get("/especialistas", response_model=list[EspecialistaRead])
async def listar_especialistas(session: AsyncSession = Depends(get_session)):
    """Cuentas de especialista activas, para elegir a quien remitir."""
    usuarios = (
        await session.execute(
            select(Usuario).where(Usuario.rol == RolUsuario.especialista, Usuario.activo.is_(True)).order_by(Usuario.nombre)
        )
    ).scalars().all()
    especialidades = {
        pid: esp
        for pid, esp in (
            await session.execute(
                select(ProfesionalTratante.usuario_id, ProfesionalTratante.especialidad).where(
                    ProfesionalTratante.usuario_id.in_([u.id for u in usuarios])
                )
            )
        )
    } if usuarios else {}
    return [EspecialistaRead(id=u.id, nombre=u.nombre, especialidad=especialidades.get(u.id)) for u in usuarios]


@router.post("/pacientes/{paciente_id}/remisiones", response_model=RemisionRead, status_code=201)
async def remitir_paciente(
    paciente_id: UUID,
    datos: RemisionCreate,
    session: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(get_current_usuario),
):
    await obtener_paciente_o_404(paciente_id, session)
    especialista = await session.get(Usuario, datos.especialista_id)
    if especialista is None or especialista.rol != RolUsuario.especialista or not especialista.activo:
        raise HTTPException(422, "El especialista no existe o no está activo.")
    vigente = (
        await session.execute(
            select(Remision.id).where(
                Remision.paciente_id == paciente_id,
                Remision.especialista_id == especialista.id,
                Remision.retirada_en.is_(None),
            )
        )
    ).first()
    if vigente is not None:
        raise HTTPException(409, "Este paciente ya está remitido a ese especialista. Retire el acceso para remitirlo de nuevo.")
    remision = Remision(
        paciente_id=paciente_id,
        especialista_id=especialista.id,
        motivo=datos.motivo,
        toda_la_boca=datos.toda_la_boca,
        creado_por=usuario.id,
    )
    session.add(remision)
    await session.flush()
    for numero in datos.dientes:
        session.add(RemisionDiente(remision_id=remision.id, numero_diente=numero))
    await session.commit()
    await session.refresh(remision)
    leida = (await _remisiones_leidas(session, [remision]))[0]
    # Aviso por correo (sin datos del paciente). Si falla no se deshace la remision: la Dra. ve que no se envio.
    leida.aviso_correo = await enviar_aviso_remision(especialista.email) if especialista.email else False
    return leida


@router.get("/pacientes/{paciente_id}/remisiones", response_model=list[RemisionRead])
async def listar_remisiones(paciente_id: UUID, session: AsyncSession = Depends(get_session)):
    """Las vigentes y las retiradas, la mas reciente primero."""
    await obtener_paciente_o_404(paciente_id, session)
    filas = (
        await session.execute(select(Remision).where(Remision.paciente_id == paciente_id).order_by(Remision.creado_en.desc()))
    ).scalars().all()
    return await _remisiones_leidas(session, list(filas))


@router.patch("/remisiones/{remision_id}/retirar", response_model=RemisionRead)
async def retirar_acceso(
    remision_id: UUID,
    session: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(get_current_usuario),
):
    """Quita el acceso del especialista a ese paciente. No borra lo que escribio."""
    remision = await session.get(Remision, remision_id)
    if remision is None:
        raise HTTPException(404, "Remisión no encontrada")
    if remision.retirada_en is not None:
        raise HTTPException(409, "El acceso ya estaba retirado")
    remision.retirada_en = ahora()
    remision.retirada_por = usuario.id
    await session.commit()
    await session.refresh(remision)
    return (await _remisiones_leidas(session, [remision]))[0]


# --- Lo que escribieron los especialistas --------------------------------------------------------------------

async def _atenciones_leidas(session: AsyncSession, atenciones: list[AtencionEspecialista]) -> list[AtencionRead]:
    dientes = await svc.dientes_por_atencion(session, [a.id for a in atenciones])
    nombres = {
        u.id: u.nombre
        for u in (await session.execute(select(Usuario).where(Usuario.id.in_([a.creado_por for a in atenciones])))).scalars()
    } if atenciones else {}
    return [
        AtencionRead.model_validate(a).model_copy(
            update={"dientes": dientes.get(a.id, []), "autor_nombre": nombres.get(a.creado_por)}
        )
        for a in atenciones
    ]


@router.get("/pacientes/{paciente_id}/atenciones-especialistas", response_model=list[AtencionRead])
async def listar_atenciones(paciente_id: UUID, session: AsyncSession = Depends(get_session)):
    await obtener_paciente_o_404(paciente_id, session)
    filas = (
        await session.execute(
            select(AtencionEspecialista)
            .where(AtencionEspecialista.paciente_id == paciente_id)
            .order_by(AtencionEspecialista.fecha.desc(), AtencionEspecialista.creado_en.desc())
        )
    ).scalars().all()
    return await _atenciones_leidas(session, list(filas))


@router.patch("/atenciones-especialistas/{atencion_id}", response_model=AtencionRead)
async def corregir_atencion(
    atencion_id: UUID,
    datos: AtencionUpdate,
    session: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(get_current_usuario),
):
    """La Dra. puede editar lo que escribe el especialista."""
    atencion = await session.get(AtencionEspecialista, atencion_id)
    if atencion is None:
        raise HTTPException(404, "Atención no encontrada")
    cambios = datos.model_dump(exclude_unset=True)
    if not cambios:
        raise HTTPException(422, "No hay ningún campo para corregir")
    dientes = cambios.pop("dientes", None)
    if "procedimiento" in cambios and cambios["procedimiento"] is None:
        raise HTTPException(422, "El procedimiento no puede quedar vacío")
    if "fecha" in cambios and cambios["fecha"] is None:
        raise HTTPException(422, "La fecha no puede quedar vacía")
    for campo, valor in cambios.items():
        setattr(atencion, campo, valor)
    if dientes is not None:
        await session.execute(delete(AtencionDiente).where(AtencionDiente.atencion_id == atencion.id))
        for numero in dientes:
            session.add(AtencionDiente(atencion_id=atencion.id, numero_diente=numero))
    atencion.actualizado_en = ahora()
    atencion.actualizado_por = usuario.id
    await session.commit()
    await session.refresh(atencion)
    return (await _atenciones_leidas(session, [atencion]))[0]


@router.delete("/atenciones-especialistas/{atencion_id}", status_code=204)
async def borrar_atencion(atencion_id: UUID, session: AsyncSession = Depends(get_session)):
    """La Dra. borra sin clave de autorizacion (la clave es para el especialista)."""
    atencion = await session.get(AtencionEspecialista, atencion_id)
    if atencion is None:
        raise HTTPException(404, "Atención no encontrada")
    await session.execute(delete(AtencionDiente).where(AtencionDiente.atencion_id == atencion.id))
    await session.delete(atencion)
    await session.commit()


@router.get("/pacientes/{paciente_id}/accesos-especialistas", response_model=list[AccesoRead])
async def listar_accesos(paciente_id: UUID, session: AsyncSession = Depends(get_session)):
    """Quien miro a este paciente (los 200 mas recientes)."""
    await obtener_paciente_o_404(paciente_id, session)
    filas = await session.execute(
        select(Usuario.nombre, AccesoPaciente.momento, AccesoPaciente.accion)
        .join(Usuario, Usuario.id == AccesoPaciente.usuario_id)
        .where(AccesoPaciente.paciente_id == paciente_id)
        .order_by(AccesoPaciente.momento.desc())
        .limit(200)
    )
    return [AccesoRead(usuario_nombre=n, momento=m, accion=a) for n, m, a in filas]


# --- Clave de autorizacion de la Dra. -----------------------------------------------------------------------

@router.put("/mi-cuenta/clave-de-autorizacion", status_code=204)
async def fijar_clave_de_autorizacion(
    datos: PinFijar,
    session: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(get_current_usuario),
):
    """6 digitos, distinta de su clave de acceso; pide la clave de acceso actual para cambiarla."""
    if not verificar_password(datos.clave_actual, usuario.password_hash):
        raise HTTPException(403, "La clave de acceso actual no es correcta.")
    if verificar_password(datos.pin, usuario.password_hash):
        raise HTTPException(422, "La clave de autorización debe ser distinta de su clave de acceso.")
    usuario.pin_autorizacion_hash = hash_password(datos.pin)
    usuario.actualizado_en = ahora()
    await session.commit()
