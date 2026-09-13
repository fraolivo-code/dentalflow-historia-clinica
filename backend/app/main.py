from fastapi import FastAPI

from app.routers import (
    consentimientos,
    odontograma,
    pacientes,
    periodontograma,
    puentes,
    usuarios,
    visitas,
)

app = FastAPI(title="Historia Clinica Digital — Fase 2")

app.include_router(usuarios.router)
app.include_router(pacientes.router)
app.include_router(visitas.router)
app.include_router(odontograma.router)
app.include_router(puentes.router)
app.include_router(periodontograma.router)
app.include_router(consentimientos.router)


@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok"}
