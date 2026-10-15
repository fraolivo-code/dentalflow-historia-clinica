from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_usuario, get_session, requerir_acceso_total, requerir_profesional_vinculado
from app.enums import EstadoHistoria
from app.models.bitacora_tratamiento import BitacoraTratamiento
from app.models.common import ahora
from app.models.examen import ExamenSolicitado
from app.models.odontograma import OdontogramaHallazgo, OdontogramaLesionApical
from app.models.tratamiento import Tratamiento
from app.models.usuario import Usuario
from app.models.visita import Visita
from app.routers.pacientes import obtener_paciente_o_404
from app.schemas.paciente import PacienteRead
from app.services import auditoria, borrado_paciente, correlativos, eliminacion_carga, paciente_cambios

# Historia en carga / aprobada (procedimiento de carga, 15/10/2026). Francisco carga bajo la
# supervision de la Dra.; mientras esta «en carga» se puede eliminar lo cargado por error;
# la Dra. la aprueba y desde ahi es oficial (no se elimina, se corrige con trazabilidad).
router = APIRouter(tags=["estado-historia"], dependencies=[Depends(requerir_acceso_total)])


class Aprobacion(BaseModel):
    confirmo: bool = False


class EliminarHistoria(BaseModel):
    numero_historia: str


@router.post("/pacientes/{paciente_id}/aprobar-historia", response_model=PacienteRead)
async def aprobar_historia(
    paciente_id: UUID,
    datos: Aprobacion,
    session: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(requerir_profesional_vinculado),
):
    """Solo la Dra.: da por revisada la historia y la vuelve oficial."""
    if datos.confirmo is not True:
        raise HTTPException(422, "Debe confirmar la aprobación de la historia.")
    paciente = await obtener_paciente_o_404(paciente_id, session)
    if paciente.estado_historia == EstadoHistoria.aprobada:
        raise HTTPException(409, "Esta historia ya está aprobada.")
    paciente.estado_historia = EstadoHistoria.aprobada
    paciente.aprobada_en = ahora()
    paciente.aprobada_por = usuario.id
    paciente_cambios.registrar(
        session, paciente.id, usuario.id, [("estado_historia", EstadoHistoria.en_carga.value, EstadoHistoria.aprobada.value)]
    )
    auditoria.registrar(session, "historia_aprobada", actor_id=usuario.id, detalle=paciente.numero_historia)
    await session.commit()
    await session.refresh(paciente)
    return paciente


@router.post("/pacientes/{paciente_id}/eliminar-historia")
async def eliminar_historia(
    paciente_id: UUID,
    datos: EliminarHistoria,
    session: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(get_current_usuario),
):
    """Elimina TODA una historia «en carga» (con confirmacion escrita de su numero). No existe para una aprobada."""
    paciente = await eliminacion_carga.exigir_en_carga(session, paciente_id)
    if not datos.numero_historia.strip().isdecimal() or not paciente.numero_historia.isdecimal() or int(
        datos.numero_historia
    ) != int(paciente.numero_historia):
        raise HTTPException(422, "Escriba el número de historia exacto para confirmar.")
    numero = paciente.numero_historia
    cuentas = await borrado_paciente.contar(session, paciente_id)
    await borrado_paciente.borrar(session, paciente_id)
    # Sin datos clinicos: solo que historia y cuantas filas.
    auditoria.registrar(
        session, "historia_en_carga_eliminada", actor_id=usuario.id,
        detalle=f"{numero}: " + ", ".join(f"{t}={n}" for t, n in sorted(cuentas.items())),
    )
    await session.commit()
    return {"eliminada": numero, "filas": cuentas}


async def _eliminar(session: AsyncSession, modelo, registro_id: UUID, nombre: str):
    registro = await session.get(modelo, registro_id)
    if registro is None:
        raise HTTPException(404, f"{nombre} no encontrado")
    await eliminacion_carga.exigir_en_carga(session, registro.paciente_id)
    return registro


@router.delete("/visitas/{visita_id}", status_code=204)
async def eliminar_visita(visita_id: UUID, session: AsyncSession = Depends(get_session)):
    await _eliminar(session, Visita, visita_id, "Visita")
    await eliminacion_carga.eliminar_registro(session, Visita, visita_id)


@router.delete("/bitacora/{entrada_id}", status_code=204)
async def eliminar_entrada_bitacora(entrada_id: UUID, session: AsyncSession = Depends(get_session)):
    await _eliminar(session, BitacoraTratamiento, entrada_id, "Entrada de bitácora")
    await eliminacion_carga.eliminar_registro(session, BitacoraTratamiento, entrada_id)


@router.delete("/tratamientos/{tratamiento_id}", status_code=204)
async def eliminar_tratamiento(tratamiento_id: UUID, session: AsyncSession = Depends(get_session)):
    await _eliminar(session, Tratamiento, tratamiento_id, "Tratamiento")
    await eliminacion_carga.eliminar_registro(session, Tratamiento, tratamiento_id)


@router.delete("/examenes/{examen_id}", status_code=204)
async def eliminar_examen(examen_id: UUID, session: AsyncSession = Depends(get_session)):
    await _eliminar(session, ExamenSolicitado, examen_id, "Examen")
    await eliminacion_carga.eliminar_registro(session, ExamenSolicitado, examen_id)


@router.delete("/hallazgos/{hallazgo_id}", status_code=204)
async def deshacer_hallazgo(hallazgo_id: UUID, session: AsyncSession = Depends(get_session)):
    """Elimina un hallazgo cargado por error; lo que se cerro al agregarlo vuelve a estar activo."""
    await _eliminar(session, OdontogramaHallazgo, hallazgo_id, "Hallazgo")
    await eliminacion_carga.reabrir_lo_que_cerro(session, hallazgo_id)
    await eliminacion_carga.eliminar_registro(session, OdontogramaHallazgo, hallazgo_id)


@router.delete("/lesiones-apicales/{lesion_id}", status_code=204)
async def eliminar_lesion_apical(lesion_id: UUID, session: AsyncSession = Depends(get_session)):
    await _eliminar(session, OdontogramaLesionApical, lesion_id, "Lesión apical")
    await eliminacion_carga.eliminar_registro(session, OdontogramaLesionApical, lesion_id)
