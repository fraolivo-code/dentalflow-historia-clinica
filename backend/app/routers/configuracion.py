# app/routers/configuracion.py — Portada configurable (Etapa 7, Parte A).
# La LECTURA es publica (tambien alimenta la pantalla de inicio de sesion): sin
# sesion y sin el cambio obligatorio de clave. La ESCRITURA es solo de las
# cuentas con acceso total.

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import undefer
from starlette.concurrency import run_in_threadpool

from app.deps import get_session, requerir_acceso_total
from app.models.common import a_utc, ahora
from app.models.configuracion_consultorio import ID_UNICO, ConfiguracionConsultorio
from app.models.usuario import Usuario
from app.schemas.configuracion import (
    NumeracionRead,
    NumeracionUpdate,
    PortadaRead,
    PortadaUpdate,
)
from app.services import auditoria, correlativos
from app.services.consultorio import nombre_por_defecto
from app.services.imagen_portada import MAX_BYTES, ImagenInvalida, procesar

router = APIRouter(prefix="/configuracion", tags=["configuracion"])

MAX_NOMBRE = 120
MAX_FRASE = 200


async def _obtener(session: AsyncSession) -> ConfiguracionConsultorio:
    """La fila unica; la migracion la crea vacia, aqui se repone si faltara."""
    config = await session.get(ConfiguracionConsultorio, ID_UNICO)
    if config is None:
        config = ConfiguracionConsultorio(id=ID_UNICO)
        session.add(config)
        await session.flush()
    return config


def _leer(config: ConfiguracionConsultorio) -> PortadaRead:
    tiene = config.imagen_tipo is not None and config.imagen_actualizada_en is not None
    return PortadaRead(
        nombre=config.nombre or nombre_por_defecto(),
        frase=config.frase,
        tiene_imagen=tiene,
        imagen_version=(
            int(a_utc(config.imagen_actualizada_en).timestamp() * 1000) if tiene else None
        ),
    )


def _limpiar(valor: str | None, maximo: int, etiqueta: str) -> str | None:
    valor = (valor or "").strip()
    if not valor:
        return None
    if len(valor) > maximo:
        raise HTTPException(422, f"{etiqueta} no puede superar {maximo} caracteres.")
    return valor


@router.get("/portada", response_model=PortadaRead)
async def leer_portada(session: AsyncSession = Depends(get_session)):
    return _leer(await _obtener(session))


@router.get("/portada/imagen")
async def leer_imagen(v: str | None = None, session: AsyncSession = Depends(get_session)):
    """`v` se ignora: solo sirve para que el navegador refresque su cache."""
    resultado = await session.execute(
        select(ConfiguracionConsultorio)
        .where(ConfiguracionConsultorio.id == ID_UNICO)
        .options(undefer(ConfiguracionConsultorio.imagen))
    )
    config = resultado.scalar_one_or_none()
    if config is None or config.imagen is None or config.imagen_tipo is None:
        raise HTTPException(404, "No hay imagen configurada.")
    return Response(
        content=config.imagen,
        media_type=config.imagen_tipo,
        headers={
            "Cache-Control": "public, max-age=86400",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.put("/portada", response_model=PortadaRead)
async def actualizar_portada(
    datos: PortadaUpdate,
    session: AsyncSession = Depends(get_session),
    actor: Usuario = Depends(requerir_acceso_total),
):
    nombre = _limpiar(datos.nombre, MAX_NOMBRE, "El nombre")
    frase = _limpiar(datos.frase, MAX_FRASE, "La frase")
    config = await _obtener(session)
    config.nombre = nombre
    config.frase = frase
    config.actualizado_por = actor.id
    config.actualizado_en = ahora()
    # Sin el contenido de los textos en la auditoria.
    auditoria.registrar(session, "configuracion_actualizada", actor_id=actor.id)
    await session.commit()
    return _leer(config)


@router.put("/portada/imagen", response_model=PortadaRead)
async def subir_imagen(
    archivo: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
    actor: Usuario = Depends(requerir_acceso_total),
):
    # Se lee un byte de mas para detectar el exceso sin cargar archivos enormes.
    datos = await archivo.read(MAX_BYTES + 1)
    try:
        contenido, tipo = await run_in_threadpool(procesar, datos)
    except ImagenInvalida as error:
        raise HTTPException(error.estado, error.mensaje)

    config = await _obtener(session)
    momento = ahora()
    config.imagen = contenido
    config.imagen_tipo = tipo
    config.imagen_actualizada_en = momento
    config.actualizado_por = actor.id
    config.actualizado_en = momento
    auditoria.registrar(session, "imagen_portada_actualizada", actor_id=actor.id)
    await session.commit()
    return _leer(config)


@router.delete("/portada/imagen", response_model=PortadaRead)
async def quitar_imagen(
    session: AsyncSession = Depends(get_session),
    actor: Usuario = Depends(requerir_acceso_total),
):
    config = await _obtener(session)
    if config.imagen_tipo is not None:
        config.imagen = None
        config.imagen_tipo = None
        config.imagen_actualizada_en = None
        config.actualizado_por = actor.id
        config.actualizado_en = ahora()
        auditoria.registrar(session, "imagen_portada_eliminada", actor_id=actor.id)
    await session.commit()
    return _leer(config)


async def _leer_numeracion(session: AsyncSession, config: ConfiguracionConsultorio) -> NumeracionRead:
    return NumeracionRead(
        siguiente_numero=await correlativos.siguiente_sin_consumir(session),
        numero_ancho=config.numero_ancho,
        mayor_existente=await correlativos.mayor_existente(session),
    )


@router.get("/numeracion", response_model=NumeracionRead)
async def leer_numeracion(
    session: AsyncSession = Depends(get_session),
    _actor: Usuario = Depends(requerir_acceso_total),
):
    return await _leer_numeracion(session, await _obtener(session))


@router.put("/numeracion", response_model=NumeracionRead)
async def configurar_numeracion(
    datos: NumeracionUpdate,
    session: AsyncSession = Depends(get_session),
    actor: Usuario = Depends(requerir_acceso_total),
):
    mayor = await correlativos.mayor_existente(session)
    if datos.siguiente_numero <= mayor:
        raise HTTPException(
            409,
            f"No se puede retroceder: ya existe la historia {mayor} y el siguiente número "
            f"debe ser mayor que {mayor}.",
        )
    config = await _obtener(session)
    config.numero_ancho = datos.numero_ancho
    config.actualizado_por = actor.id
    config.actualizado_en = ahora()
    await correlativos.fijar_siguiente(session, datos.siguiente_numero)
    auditoria.registrar(
        session,
        "numeracion_configurada",
        actor_id=actor.id,
        detalle=f"siguiente={datos.siguiente_numero}, ancho={datos.numero_ancho}",
    )
    await session.commit()
    return await _leer_numeracion(session, config)
