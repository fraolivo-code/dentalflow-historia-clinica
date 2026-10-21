# app/routers/especialista.py — Lo unico que puede hacer una cuenta con rol especialista (19/10/2026).
# El resto del sistema le responde 403 (ver deps.get_usuario_autenticado). Cada respuesta es una lista blanca
# de campos (schemas/especialista.py); ve solo los pacientes que la Dra. le remitio y mientras no retire el acceso.
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session, requerir_especialista
from app.models.antecedente import Antecedente, PacienteAntecedente
from app.models.bitacora_tratamiento import BitacoraDiente, BitacoraTratamiento
from app.models.common import ahora
from app.models.examen import ExamenSolicitado
from app.models.odontograma import OdontogramaHallazgo, OdontogramaLesionApical
from app.models.paciente import Paciente
from app.models.profesional_tratante import ProfesionalTratante
from app.models.receta import Receta
from app.models.remision import AtencionDiente, AtencionEspecialista, Remision
from app.models.usuario import Usuario
from app.schemas.especialista import (
    AntecedenteEspecialista,
    ExamenEspecialista,
    FichaEspecialista,
    HallazgoEspecialista,
    LesionEspecialista,
    NotaEspecialista,
    OdontogramaEspecialista,
    PacienteDeEspecialista,
    PacienteEspecialista,
    RemisionEspecialista,
)
from app.routers.medicamentos import listar_medicamentos
from app.schemas.profesional_tratante import ProfesionalTratanteRead, ProfesionalTratanteUpdate
from app.routers.recetas import _con_medicamentos, emitir_receta, pdf_de_receta
from app.schemas.receta import MedicamentoRead, RecetaCreate, RecetaRead
from app.schemas.remision import AtencionCreate, AtencionRead
from app.services import especialista as svc

router = APIRouter(prefix="/especialista", tags=["especialista"])


@router.get("/pacientes", response_model=list[PacienteDeEspecialista])
async def mis_pacientes(
    session: AsyncSession = Depends(get_session), usuario: Usuario = Depends(requerir_especialista)
):
    """Los pacientes que la Dra. le remitio y cuyo acceso sigue vigente."""
    filas = await session.execute(
        select(Remision, Paciente)
        .join(Paciente, Paciente.id == Remision.paciente_id)
        .where(Remision.especialista_id == usuario.id, Remision.retirada_en.is_(None))
        .order_by(Remision.creado_en.desc())
    )
    return [
        PacienteDeEspecialista(
            id=p.id,
            numero_historia=p.numero_historia,
            nombre_completo=p.nombre_completo,
            edad=svc.edad_en_anios(p.fecha_nacimiento),
            movil=p.movil,
            email=p.email,
            motivo=r.motivo,
            remision_id=r.id,
            remitido_en=r.creado_en,
        )
        for r, p in filas
    ]


@router.get("/pacientes/{paciente_id}/ficha", response_model=FichaEspecialista)
async def ficha_del_paciente(
    paciente_id: UUID,
    session: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(requerir_especialista),
):
    remision = await svc.remision_activa(session, usuario, paciente_id)
    paciente = await session.get(Paciente, paciente_id)
    dientes_remision = (await svc.dientes_por_remision(session, [remision.id])).get(remision.id, [])

    antecedentes = (
        await session.execute(
            select(Antecedente.nombre, PacienteAntecedente.detalle)
            .join(PacienteAntecedente, PacienteAntecedente.antecedente_id == Antecedente.id)
            .where(PacienteAntecedente.paciente_id == paciente_id, PacienteAntecedente.presente.is_(True))
            .order_by(Antecedente.nombre)
        )
    ).all()
    examenes = (
        await session.execute(
            select(ExamenSolicitado)
            .where(ExamenSolicitado.paciente_id == paciente_id)
            .order_by(ExamenSolicitado.fecha_indicacion.desc())
        )
    ).scalars().all()

    # Notas ligadas a los dientes de la remision (con «toda la boca», a cualquier diente). Sin dientes no se comparten.
    entradas = (
        await session.execute(
            select(BitacoraTratamiento)
            .where(BitacoraTratamiento.paciente_id == paciente_id)
            .order_by(BitacoraTratamiento.fecha.desc(), BitacoraTratamiento.creado_en.desc())
        )
    ).scalars().all()
    por_entrada: dict[UUID, list[int]] = {}
    if entradas:
        for bitacora_id, diente in await session.execute(
            select(BitacoraDiente.bitacora_id, BitacoraDiente.numero_diente).where(
                BitacoraDiente.bitacora_id.in_([e.id for e in entradas])
            )
        ):
            por_entrada.setdefault(bitacora_id, []).append(diente)
    area = set(dientes_remision)
    notas = []
    for e in entradas:
        dientes = sorted(set(por_entrada.get(e.id, [])) | ({e.numero_diente} if e.numero_diente else set()))
        if not dientes:
            continue
        if remision.toda_la_boca or area.intersection(dientes):
            notas.append(NotaEspecialista(fecha=e.fecha, descripcion=e.descripcion, dientes=dientes))

    svc.registrar_acceso(session, usuario.id, paciente_id, "ficha")
    await session.commit()
    return FichaEspecialista(
        paciente=PacienteEspecialista(
            id=paciente.id,
            numero_historia=paciente.numero_historia,
            nombre_completo=paciente.nombre_completo,
            edad=svc.edad_en_anios(paciente.fecha_nacimiento),
            movil=paciente.movil,
            telefono_fijo=paciente.telefono_fijo,
            email=paciente.email,
            alerta=paciente.alerta,
            alerta_texto=paciente.alerta_texto,
            fuma=paciente.fuma,
            fuma_detalle=paciente.fuma_detalle,
            medicamentos_actuales=paciente.medicamentos_actuales,
            medicamentos_actuales_detalle=paciente.medicamentos_actuales_detalle,
            tratamiento_medico_actual=paciente.tratamiento_medico_actual,
            denticion=paciente.denticion,
        ),
        remision=RemisionEspecialista(
            id=remision.id,
            motivo=remision.motivo,
            dientes=dientes_remision,
            toda_la_boca=remision.toda_la_boca,
            remitido_en=remision.creado_en,
        ),
        antecedentes=[AntecedenteEspecialista(nombre=n, detalle=d) for n, d in antecedentes],
        examenes=[
            ExamenEspecialista(
                tipo=x.tipo,
                descripcion=x.descripcion,
                fecha_indicacion=x.fecha_indicacion,
                estado=x.estado,
                fecha_traido=x.fecha_traido,
                hallazgos=x.hallazgos,
                enlace=x.enlace,
            )
            for x in examenes
        ],
        notas=notas,
    )


@router.get("/pacientes/{paciente_id}/odontograma", response_model=OdontogramaEspecialista)
async def odontograma_del_paciente(
    paciente_id: UUID,
    session: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(requerir_especialista),
):
    """Odontograma vigente, solo lectura."""
    await svc.remision_activa(session, usuario, paciente_id)
    hallazgos = (
        await session.execute(
            select(OdontogramaHallazgo).where(
                OdontogramaHallazgo.paciente_id == paciente_id, OdontogramaHallazgo.resuelto.is_(False)
            )
        )
    ).scalars().all()
    lesiones = (
        await session.execute(
            select(OdontogramaLesionApical).where(
                OdontogramaLesionApical.paciente_id == paciente_id, OdontogramaLesionApical.resuelto.is_(False)
            )
        )
    ).scalars().all()
    svc.registrar_acceso(session, usuario.id, paciente_id, "odontograma")
    await session.commit()
    return OdontogramaEspecialista(
        hallazgos=[
            HallazgoEspecialista(
                id=h.id,
                numero_diente=h.numero_diente,
                tipo_hallazgo=h.tipo_hallazgo,
                superficie=h.superficie,
                fecha=h.fecha,
                rehabilitado=h.rehabilitado,
            )
            for h in hallazgos
        ],
        lesiones=[
            LesionEspecialista(id=l.id, numero_diente=l.numero_diente, raiz=l.raiz, tipo=l.tipo, fecha=l.fecha)
            for l in lesiones
        ],
    )


# --- Su propia atencion -------------------------------------------------------------------------------------

async def _leidas(session: AsyncSession, atenciones: list[AtencionEspecialista], autor: str) -> list[AtencionRead]:
    dientes = await svc.dientes_por_atencion(session, [a.id for a in atenciones])
    return [
        AtencionRead.model_validate(a).model_copy(update={"dientes": dientes.get(a.id, []), "autor_nombre": autor})
        for a in atenciones
    ]


@router.post("/pacientes/{paciente_id}/atenciones", response_model=AtencionRead, status_code=201)
async def registrar_atencion(
    paciente_id: UUID,
    datos: AtencionCreate,
    session: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(requerir_especialista),
):
    """Lo que hizo el especialista; queda firmado por el."""
    remision = await svc.remision_activa(session, usuario, paciente_id)
    atencion = AtencionEspecialista(
        paciente_id=paciente_id,
        remision_id=remision.id,
        fecha=datos.fecha,
        procedimiento=datos.procedimiento,
        descripcion=datos.descripcion,
        indicaciones=datos.indicaciones,
        creado_por=usuario.id,
    )
    session.add(atencion)
    await session.flush()
    for numero in datos.dientes:
        session.add(AtencionDiente(atencion_id=atencion.id, numero_diente=numero))
    svc.registrar_acceso(session, usuario.id, paciente_id, "atencion_registrada")
    await session.commit()
    await session.refresh(atencion)
    return (await _leidas(session, [atencion], usuario.nombre))[0]


@router.get("/pacientes/{paciente_id}/atenciones", response_model=list[AtencionRead])
async def mis_atenciones(
    paciente_id: UUID,
    session: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(requerir_especialista),
):
    """Solo las suyas (no las de otros especialistas)."""
    await svc.remision_activa(session, usuario, paciente_id)
    filas = (
        await session.execute(
            select(AtencionEspecialista)
            .where(AtencionEspecialista.paciente_id == paciente_id, AtencionEspecialista.creado_por == usuario.id)
            .order_by(AtencionEspecialista.fecha.desc(), AtencionEspecialista.creado_en.desc())
        )
    ).scalars().all()
    return await _leidas(session, list(filas), usuario.nombre)


@router.delete("/atenciones/{atencion_id}", status_code=204)
async def borrar_mi_atencion(
    atencion_id: UUID,
    session: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(requerir_especialista),
    x_clave_autorizacion: str | None = Header(default=None),
):
    """Solo lo que el escribio y con la clave de autorizacion de la Dra. (encabezado X-Clave-Autorizacion)."""
    atencion = await session.get(AtencionEspecialista, atencion_id)
    if atencion is None or atencion.creado_por != usuario.id:
        raise HTTPException(404, "Atención no encontrada")
    await svc.remision_activa(session, usuario, atencion.paciente_id)
    dra = await svc.autorizar_con_pin(session, usuario, x_clave_autorizacion)
    svc.registrar_acceso(session, usuario.id, atencion.paciente_id, f"atencion_borrada (autorizo {dra.nombre})")
    await session.execute(delete(AtencionDiente).where(AtencionDiente.atencion_id == atencion.id))
    await session.delete(atencion)
    await session.commit()


# --- Sus recetas --------------------------------------------------------------------------------------------
# Salen firmadas con su propio profesional (COV y MPPS). Sin visita ni tratamiento (son de la Dra.).

@router.get("/medicamentos", response_model=list[MedicamentoRead])
async def medicamentos(
    buscar: str | None = None,
    session: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(requerir_especialista),
):
    """Catalogo de medicamentos, para el autocompletar."""
    return await listar_medicamentos(buscar, session)


@router.post("/pacientes/{paciente_id}/recetas", response_model=RecetaRead, status_code=201)
async def emitir_mi_receta(
    paciente_id: UUID,
    datos: RecetaCreate,
    session: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(requerir_especialista),
):
    await svc.remision_activa(session, usuario, paciente_id)
    if datos.visita_id is not None or datos.tratamiento_id is not None:
        raise HTTPException(422, "Una receta del especialista no se liga a visitas ni a tratamientos de la Dra.")
    receta = await emitir_receta(session, usuario, paciente_id, datos)
    svc.registrar_acceso(session, usuario.id, paciente_id, "receta_emitida")
    await session.commit()
    return receta


async def _mi_receta_o_404(session: AsyncSession, usuario: Usuario, paciente_id: UUID, receta_id: UUID) -> Receta:
    await svc.remision_activa(session, usuario, paciente_id)
    receta = await session.get(Receta, receta_id)
    if receta is None or receta.paciente_id != paciente_id or receta.creado_por != usuario.id:
        raise HTTPException(404, "Récipe no encontrado")
    return receta


@router.get("/pacientes/{paciente_id}/recetas", response_model=list[RecetaRead])
async def mis_recetas(
    paciente_id: UUID,
    session: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(requerir_especialista),
):
    """Solo las que emitio el (no las de la Dra. ni las de otros especialistas)."""
    await svc.remision_activa(session, usuario, paciente_id)
    filas = (
        await session.execute(
            select(Receta)
            .where(Receta.paciente_id == paciente_id, Receta.creado_por == usuario.id)
            .order_by(Receta.fecha.desc(), Receta.creado_en.desc())
        )
    ).scalars().all()
    return await _con_medicamentos(session, list(filas))


@router.get("/pacientes/{paciente_id}/recetas/{receta_id}/pdf")
async def pdf_mi_receta(
    paciente_id: UUID,
    receta_id: UUID,
    session: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(requerir_especialista),
):
    await _mi_receta_o_404(session, usuario, paciente_id, receta_id)
    return await pdf_de_receta(paciente_id, receta_id, session, "receta.html", "recipe")


@router.get("/pacientes/{paciente_id}/recetas/{receta_id}/pdf-indicaciones")
async def pdf_mis_indicaciones(
    paciente_id: UUID,
    receta_id: UUID,
    session: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(requerir_especialista),
):
    await _mi_receta_o_404(session, usuario, paciente_id, receta_id)
    return await pdf_de_receta(
        paciente_id, receta_id, session, "indicaciones_medicamentos.html", "indicaciones-medicamentos"
    )


# --- Sus datos profesionales (membrete de sus recetas) --------------------------------------------------------

async def _mi_profesional(session: AsyncSession, usuario: Usuario) -> ProfesionalTratante:
    profesional = (
        await session.execute(select(ProfesionalTratante).where(ProfesionalTratante.usuario_id == usuario.id))
    ).scalar_one_or_none()
    if profesional is None:
        raise HTTPException(409, "Su cuenta aún no está vinculada a un profesional. Pídale a la Dra. que la vincule.")
    return profesional


@router.get("/mi-perfil", response_model=ProfesionalTratanteRead)
async def mi_perfil(session: AsyncSession = Depends(get_session), usuario: Usuario = Depends(requerir_especialista)):
    return await _mi_profesional(session, usuario)


@router.patch("/mi-perfil", response_model=ProfesionalTratanteRead)
async def actualizar_mi_perfil(
    datos: ProfesionalTratanteUpdate,
    session: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(requerir_especialista),
):
    """Completa o corrige su propio membrete. Solo su profesional, nunca el de otro."""
    profesional = await _mi_profesional(session, usuario)
    cambios = datos.model_dump(exclude_unset=True)
    if "nombre" in cambios and cambios["nombre"] is None:
        raise HTTPException(422, "El nombre no puede quedar vacío")
    for campo, valor in cambios.items():
        setattr(profesional, campo, valor)
    await session.commit()
    await session.refresh(profesional)
    return profesional

