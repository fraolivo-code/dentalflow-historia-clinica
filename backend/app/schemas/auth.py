from pydantic import BaseModel


class LoginRequest(BaseModel):
    nombre: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class CambiarClaveRequest(BaseModel):
    clave_actual: str
    clave_nueva: str


class OlvideClaveRequest(BaseModel):
    email: str


class RestablecerClaveRequest(BaseModel):
    token: str
    clave_nueva: str


class MensajeResponse(BaseModel):
    mensaje: str
