# app/routers/vinculacion.py — Etapa 6, A.3: endpoints internos de SOLO LECTURA
# para Alma. Se autentican con X-Api-Key (VINCULACION_API_KEY), no con JWT.
# Devuelven lo minimo: sin nombres (salvo el de saludo), cantidades ni datos clinicos.

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session, requerir_clave_servicio
from app.services.vinculacion import (
    evaluar_coincidencia,
    pacientes_con_movil,
    registrar_consulta,
)

router = APIRouter(
    prefix="/interno/vinculacion",
    tags=["vinculacion"],
    dependencies=[Depends(requerir_clave_servicio)],
)


class RegistradoIn(BaseModel):
    telefono: str = Field(max_length=50)


class VerificarIn(BaseModel):
    telefono: str = Field(max_length=50)
    nombre: str = Field(max_length=300)


@router.post("/registrado")
async def registrado(datos: RegistradoIn, session: AsyncSession = Depends(get_session)):
    esta = bool(await pacientes_con_movil(session, datos.telefono))
    resultado = "registrado" if esta else "no_registrado"
    await registrar_consulta(session, "registrado", datos.telefono, resultado)
    return {"registrado": esta}


@router.post("/verificar")
async def verificar(datos: VerificarIn, session: AsyncSession = Depends(get_session)):
    candidatos = await pacientes_con_movil(session, datos.telefono)
    respuesta = evaluar_coincidencia(candidatos, datos.nombre)
    if respuesta["coincide"]:
        resultado = "coincide"
    elif respuesta.get("pedir_apellido"):
        resultado = "pedir_apellido"
    else:
        resultado = "no_coincide"
    await registrar_consulta(session, "verificar", datos.telefono, resultado)
    return respuesta
