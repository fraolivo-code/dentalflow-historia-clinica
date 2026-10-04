from pydantic import BaseModel


class PortadaRead(BaseModel):
    nombre: str
    frase: str | None = None
    tiene_imagen: bool
    # Marca de tiempo (ms) de la ultima imagen: cambia al subir otra.
    imagen_version: int | None = None


class PortadaUpdate(BaseModel):
    nombre: str | None = None
    frase: str | None = None
