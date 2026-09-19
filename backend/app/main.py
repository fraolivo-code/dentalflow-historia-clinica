from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import (
    antecedentes,
    auth,
    bitacora,
    consentimientos,
    observaciones,
    odontograma,
    pacientes,
    periodontograma,
    profesionales_tratantes,
    puentes,
    tratamientos,
    usuarios,
    visitas,
)

app = FastAPI(title="Historia Clinica Digital — Fase 2")

# Abierto a cualquier origen mientras el frontend no tiene un dominio fijo en
# Railway (Etapa 3). Restringir al dominio real una vez desplegado.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(usuarios.router)
app.include_router(pacientes.router)
app.include_router(visitas.router)
app.include_router(odontograma.router)
app.include_router(puentes.router)
app.include_router(periodontograma.router)
app.include_router(consentimientos.router)
app.include_router(antecedentes.router)
app.include_router(profesionales_tratantes.router)
app.include_router(tratamientos.router)
app.include_router(bitacora.router)
app.include_router(observaciones.router)


@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok"}
