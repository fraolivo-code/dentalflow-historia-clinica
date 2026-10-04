from pydantic import BaseModel, Field

MAX_ANCHO = 12
MAX_NUMERO = 10**12 - 1


class PortadaRead(BaseModel):
    nombre: str
    frase: str | None = None
    tiene_imagen: bool
    # Marca de tiempo (ms) de la ultima imagen: cambia al subir otra.
    imagen_version: int | None = None


class PortadaUpdate(BaseModel):
    nombre: str | None = None
    frase: str | None = None


class NumeracionRead(BaseModel):
    siguiente_numero: int
    numero_ancho: int
    # El numero de historia mas alto en uso (0 si no hay ninguno), como referencia.
    mayor_existente: int


class NumeracionUpdate(BaseModel):
    siguiente_numero: int = Field(ge=1, le=MAX_NUMERO)
    numero_ancho: int = Field(ge=1, le=MAX_ANCHO)
