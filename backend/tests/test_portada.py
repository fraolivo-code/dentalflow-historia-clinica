# Etapa 7, Parte A: portada configurable (sin red y sin Postgres).
# Especificacion: especificacion-tecnica-portada-configurable.md, A.2 y A.3.

import io

import pytest
import pytest_asyncio
from PIL import Image
from sqlalchemy import select

from app import security
from app.enums import RolUsuario
from app.models import AuditoriaUsuario, ConfiguracionConsultorio, Usuario
from app.services import imagen_portada

UN_MB = 1024 * 1024


# ------------------------------------------------------------------ utilidades


def _png(tamano=(40, 30), modo="RGB", color=(200, 30, 30)) -> bytes:
    buf = io.BytesIO()
    Image.new(modo, tamano, color).save(buf, format="PNG")
    return buf.getvalue()


def _jpeg(tamano=(40, 30), exif=None) -> bytes:
    buf = io.BytesIO()
    kwargs = {"exif": exif} if exif is not None else {}
    Image.new("RGB", tamano, (10, 120, 200)).save(buf, format="JPEG", **kwargs)
    return buf.getvalue()


def _webp(tamano=(40, 30)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", tamano, (10, 200, 60)).save(buf, format="WEBP")
    return buf.getvalue()


def _gif() -> bytes:
    buf = io.BytesIO()
    Image.new("P", (10, 10)).save(buf, format="GIF")
    return buf.getvalue()


SVG = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'


def _exif_con_gps() -> Image.Exif:
    exif = Image.Exif()
    exif[0x010F] = "MarcaDePrueba"  # Make
    exif[0x0110] = "ModeloDePrueba"  # Model
    exif[0x8825] = {  # GPSInfo: 10 N, 66 O (Caracas)
        1: "N",
        2: (10.0, 30.0, 0.0),
        3: "W",
        4: (66.0, 54.0, 0.0),
    }
    return exif


def _abrir(contenido: bytes) -> Image.Image:
    img = Image.open(io.BytesIO(contenido))
    img.load()
    return img


@pytest_asyncio.fixture
async def usuarios(session_factory):
    ids = {}
    async with session_factory() as s:
        for nombre, rol in (("doctora", RolUsuario.dra), ("asistente", RolUsuario.asistente)):
            u = Usuario(nombre=nombre, rol=rol, password_hash="x", email=f"{nombre}@e.com")
            s.add(u)
            await s.flush()
            ids[nombre] = u.id
        await s.commit()
    return ids


@pytest.fixture
def h_dra(usuarios):
    return {"Authorization": f"Bearer {security.crear_access_token(usuarios['doctora'], 'dra')}"}


@pytest.fixture
def h_asistente(usuarios):
    token = security.crear_access_token(usuarios["asistente"], "asistente")
    return {"Authorization": f"Bearer {token}"}


def _archivo(contenido: bytes, nombre="portada.png", tipo="image/png"):
    return {"archivo": (nombre, contenido, tipo)}


async def _subir(client, h, contenido, nombre="portada.png", tipo="image/png"):
    return await client.put(
        "/configuracion/portada/imagen", headers=h, files=_archivo(contenido, nombre, tipo)
    )


# -------------------------------------------------------------- lectura publica


async def test_lectura_publica_sin_configuracion_usa_el_nombre_del_producto(client, monkeypatch):
    monkeypatch.setenv("NOMBRE_PRODUCTO", "ProductoDePrueba")
    r = await client.get("/configuracion/portada")  # sin sesion
    assert r.status_code == 200
    assert r.json() == {
        "nombre": "ProductoDePrueba",
        "frase": None,
        "tiene_imagen": False,
        "imagen_version": None,
    }
    assert (await client.get("/configuracion/portada/imagen")).status_code == 404


async def test_nombre_por_defecto_es_dentalflow(client, monkeypatch):
    monkeypatch.delenv("NOMBRE_PRODUCTO", raising=False)
    assert (await client.get("/configuracion/portada")).json()["nombre"] == "DentalFlow"


async def test_lectura_publica_con_configuracion(client, h_dra):
    r = await client.put(
        "/configuracion/portada",
        headers=h_dra,
        json={"nombre": "Od. Leonor Granados", "frase": "Sonríe desde adentro"},
    )
    assert r.status_code == 200
    r = await client.get("/configuracion/portada")  # sin sesion
    assert r.json()["nombre"] == "Od. Leonor Granados"
    assert r.json()["frase"] == "Sonríe desde adentro"


async def test_lectura_publica_no_la_afecta_el_cambio_obligatorio(client, session_factory, usuarios):
    async with session_factory() as s:
        (await s.get(Usuario, usuarios["doctora"])).debe_cambiar_clave = True
        await s.commit()
    assert (await client.get("/configuracion/portada")).status_code == 200
    assert (await client.get("/configuracion/portada/imagen")).status_code == 404


# ---------------------------------------------------------------- PUT de textos


async def test_put_textos_recorta_y_vacio_es_nulo(client, h_dra, session_factory):
    r = await client.put(
        "/configuracion/portada", headers=h_dra, json={"nombre": "  Clinica  ", "frase": "   "}
    )
    assert r.status_code == 200 and r.json()["nombre"] == "Clinica" and r.json()["frase"] is None
    async with session_factory() as s:
        fila = await s.get(ConfiguracionConsultorio, 1)
        assert fila.nombre == "Clinica" and fila.frase is None
    # Vacio o ausente: el nombre vuelve al del producto.
    r = await client.put("/configuracion/portada", headers=h_dra, json={"nombre": "", "frase": None})
    assert r.json()["nombre"] == "DentalFlow"
    r = await client.put("/configuracion/portada", headers=h_dra, json={})
    assert r.status_code == 200 and r.json()["frase"] is None


async def test_put_textos_limites(client, h_dra):
    r = await client.put("/configuracion/portada", headers=h_dra, json={"nombre": "n" * 120})
    assert r.status_code == 200
    r = await client.put("/configuracion/portada", headers=h_dra, json={"frase": "f" * 200})
    assert r.status_code == 200
    r = await client.put("/configuracion/portada", headers=h_dra, json={"nombre": "n" * 121})
    assert r.status_code == 422 and "120" in r.json()["detail"]
    r = await client.put("/configuracion/portada", headers=h_dra, json={"frase": "f" * 201})
    assert r.status_code == 422 and "200" in r.json()["detail"]
    # El recorte va antes del limite: 200 + espacios sigue valiendo.
    r = await client.put("/configuracion/portada", headers=h_dra, json={"frase": "  " + "f" * 200 + "  "})
    assert r.status_code == 200


async def test_escritura_exige_acceso_total(client, h_asistente, usuarios):
    cuerpo = {"nombre": "x"}
    assert (await client.put("/configuracion/portada", json=cuerpo)).status_code == 401
    r = await client.put("/configuracion/portada", headers=h_asistente, json=cuerpo)
    assert r.status_code == 403
    for llamada in (
        lambda: _subir(client, {}, _png()),
        lambda: client.delete("/configuracion/portada/imagen"),
    ):
        assert (await llamada()).status_code == 401
    assert (await _subir(client, h_asistente, _png())).status_code == 403
    r = await client.delete("/configuracion/portada/imagen", headers=h_asistente)
    assert r.status_code == 403
    # Nada cambio.
    assert (await client.get("/configuracion/portada")).json()["tiene_imagen"] is False


async def test_escritura_bloqueada_con_cambio_de_clave_pendiente(client, h_dra, session_factory, usuarios):
    async with session_factory() as s:
        (await s.get(Usuario, usuarios["doctora"])).debe_cambiar_clave = True
        await s.commit()
    r = await client.put("/configuracion/portada", headers=h_dra, json={"nombre": "x"})
    assert r.status_code == 403 and r.json()["detail"]["codigo"] == "debe_cambiar_clave"


# ------------------------------------------------------------------ subir imagen


@pytest.mark.parametrize(
    "contenido,tipo",
    [(_png(), "image/png"), (_jpeg(), "image/jpeg"), (_webp(), "image/webp")],
    ids=["png", "jpeg", "webp"],
)
async def test_subida_valida_y_lectura_publica(client, h_dra, contenido, tipo):
    r = await _subir(client, h_dra, contenido, tipo=tipo)
    assert r.status_code == 200, r.text
    assert r.json()["tiene_imagen"] is True and r.json()["imagen_version"]

    # Se sirve sin sesion, con el tipo real y las cabeceras de seguridad/cache.
    pedido = await client.get("/configuracion/portada/imagen", params={"v": "123"})
    assert pedido.status_code == 200
    assert pedido.headers["content-type"] == tipo
    assert pedido.headers["cache-control"] == "public, max-age=86400"
    assert pedido.headers["x-content-type-options"] == "nosniff"
    assert _abrir(pedido.content).size == (40, 30)


async def test_el_tipo_se_decide_por_el_contenido_no_por_lo_declarado(client, h_dra):
    r = await _subir(client, h_dra, _jpeg(), nombre="foto.png", tipo="image/png")
    assert r.status_code == 200
    pedido = await client.get("/configuracion/portada/imagen")
    assert pedido.headers["content-type"] == "image/jpeg"


async def test_imagen_version_cambia_al_subir_otra(client, h_dra):
    primera = (await _subir(client, h_dra, _png())).json()["imagen_version"]
    segunda = (await _subir(client, h_dra, _png(color=(0, 0, 0)))).json()["imagen_version"]
    assert primera != segunda
    assert (await client.get("/configuracion/portada")).json()["imagen_version"] == segunda


@pytest.mark.parametrize(
    "contenido,nombre",
    [
        (SVG, "logo.svg"),
        (SVG, "logo.png"),  # SVG renombrado
        (_gif(), "animada.gif"),
        (_gif(), "animada.png"),  # GIF renombrado
        (b"esto es solo texto", "nota.png"),  # texto renombrado
        (b"", "vacio.png"),
        (b"\x89PNG\r\n\x1a\n" + b"no es una imagen", "roto.png"),  # firma valida, contenido falso
        (_png()[:60], "cortado.png"),  # PNG truncado
    ],
    ids=["svg", "svg-como-png", "gif", "gif-como-png", "texto", "vacio", "firma-falsa", "truncado"],
)
async def test_rechaza_formatos_no_admitidos(client, h_dra, contenido, nombre):
    r = await _subir(client, h_dra, contenido, nombre=nombre)
    assert r.status_code == 415
    assert r.json()["detail"] == "Formato no admitido. Use PNG, JPG o WebP."
    assert (await client.get("/configuracion/portada")).json()["tiene_imagen"] is False


async def test_rechaza_mas_de_1_mb(client, h_dra):
    r = await _subir(client, h_dra, b"\x89PNG\r\n\x1a\n" + b"0" * UN_MB)
    assert r.status_code == 413
    assert r.json()["detail"] == "La imagen supera el máximo de 1 MB."
    assert (await client.get("/configuracion/portada")).json()["tiene_imagen"] is False


async def test_acepta_exactamente_1_mb_en_el_limite():
    # La validacion de tamano es "mas de 1 MB": 1 MB justo pasa a la siguiente etapa.
    relleno = b"\x89PNG\r\n\x1a\n" + b"0" * (UN_MB - 8)
    assert len(relleno) == UN_MB
    with pytest.raises(imagen_portada.ImagenInvalida) as error:
        imagen_portada.procesar(relleno)
    assert error.value.estado == 415  # no es 413: el tamano no es el problema


async def test_rechaza_imagen_con_dimensiones_enormes(client, h_dra):
    buf = io.BytesIO()
    Image.new("1", (20_000, 20_000)).save(buf, format="PNG")  # pocos bytes, 400 M de pixeles
    assert len(buf.getvalue()) < UN_MB
    r = await _subir(client, h_dra, buf.getvalue())
    assert r.status_code == 413 and "dimensiones" in r.json()["detail"]


async def test_reduce_a_1200_px_conservando_proporcion(client, h_dra):
    r = await _subir(client, h_dra, _png(tamano=(2400, 1200)))
    assert r.status_code == 200
    img = _abrir((await client.get("/configuracion/portada/imagen")).content)
    assert img.size == (1200, 600) and img.format == "PNG"

    r = await _subir(client, h_dra, _jpeg(tamano=(900, 2700)))
    img = _abrir((await client.get("/configuracion/portada/imagen")).content)
    assert img.size == (400, 1200) and img.format == "JPEG"

    # Una imagen chica no se agranda.
    await _subir(client, h_dra, _webp(tamano=(300, 200)))
    assert _abrir((await client.get("/configuracion/portada/imagen")).content).size == (300, 200)


async def test_png_con_transparencia_sigue_siendo_png_con_transparencia(client, h_dra):
    original = Image.new("RGBA", (50, 50), (255, 0, 0, 0))  # totalmente transparente
    original.putpixel((10, 10), (0, 0, 255, 255))
    buf = io.BytesIO()
    original.save(buf, format="PNG")
    assert (await _subir(client, h_dra, buf.getvalue())).status_code == 200
    img = _abrir((await client.get("/configuracion/portada/imagen")).content)
    assert img.format == "PNG" and img.mode == "RGBA"
    assert img.getpixel((0, 0))[3] == 0 and img.getpixel((10, 10)) == (0, 0, 255, 255)


async def test_png_de_paleta_con_transparencia_conserva_el_alfa(client, h_dra):
    paleta = Image.new("P", (20, 20), 0)
    paleta.putpalette([255, 0, 0, 0, 255, 0] + [0] * 250)
    buf = io.BytesIO()
    paleta.save(buf, format="PNG", transparency=0)
    assert (await _subir(client, h_dra, buf.getvalue())).status_code == 200
    img = _abrir((await client.get("/configuracion/portada/imagen")).content)
    assert img.format == "PNG" and img.mode == "RGBA" and img.getpixel((0, 0))[3] == 0


async def test_elimina_los_metadatos_exif_y_gps(client, h_dra):
    original = _jpeg(exif=_exif_con_gps())
    exif_original = _abrir(original).getexif()
    assert exif_original.get(0x010F) == "MarcaDePrueba"  # el de prueba si trae metadatos
    assert exif_original.get_ifd(0x8825)

    assert (await _subir(client, h_dra, original, tipo="image/jpeg")).status_code == 200
    guardado = (await client.get("/configuracion/portada/imagen")).content
    exif = _abrir(guardado).getexif()
    assert len(exif) == 0 and not exif.get_ifd(0x8825)
    for rastro in (b"MarcaDePrueba", b"ModeloDePrueba", b"Exif", b"GPS"):
        assert rastro not in guardado


async def test_elimina_texto_y_perfiles_de_un_png(client, h_dra):
    from PIL.PngImagePlugin import PngInfo

    info = PngInfo()
    info.add_text("Author", "AutorSecreto")
    buf = io.BytesIO()
    Image.new("RGB", (20, 20)).save(buf, format="PNG", pnginfo=info, icc_profile=b"perfil-falso")
    assert b"AutorSecreto" in buf.getvalue()
    assert (await _subir(client, h_dra, buf.getvalue())).status_code == 200
    guardado = (await client.get("/configuracion/portada/imagen")).content
    assert b"AutorSecreto" not in guardado and not _abrir(guardado).info.get("icc_profile")


async def test_aplica_la_orientacion_antes_de_borrar_el_exif(client, h_dra):
    exif = Image.Exif()
    exif[0x0112] = 6  # girada: hay que rotarla 90 grados
    assert (await _subir(client, h_dra, _jpeg(tamano=(60, 20), exif=exif))).status_code == 200
    img = _abrir((await client.get("/configuracion/portada/imagen")).content)
    assert img.size == (20, 60)


# -------------------------------------------------------------------- DELETE


async def test_delete_quita_la_imagen(client, h_dra):
    await _subir(client, h_dra, _png())
    assert (await client.get("/configuracion/portada/imagen")).status_code == 200
    r = await client.delete("/configuracion/portada/imagen", headers=h_dra)
    assert r.status_code == 200
    assert r.json()["tiene_imagen"] is False and r.json()["imagen_version"] is None
    assert (await client.get("/configuracion/portada/imagen")).status_code == 404
    assert (await client.get("/configuracion/portada")).json()["tiene_imagen"] is False
    # Repetirlo no falla.
    assert (await client.delete("/configuracion/portada/imagen", headers=h_dra)).status_code == 200


async def test_delete_no_borra_los_textos(client, h_dra):
    await client.put("/configuracion/portada", headers=h_dra, json={"nombre": "Clinica", "frase": "Hola"})
    await _subir(client, h_dra, _png())
    await client.delete("/configuracion/portada/imagen", headers=h_dra)
    cuerpo = (await client.get("/configuracion/portada")).json()
    assert cuerpo["nombre"] == "Clinica" and cuerpo["frase"] == "Hola"


# ----------------------------------------------------------------- auditoria


async def test_auditoria_sin_contenido(client, h_dra, usuarios, session_factory):
    await client.put(
        "/configuracion/portada",
        headers=h_dra,
        json={"nombre": "NombreConfidencial", "frase": "FraseConfidencial"},
    )
    await _subir(client, h_dra, _jpeg(exif=_exif_con_gps()), tipo="image/jpeg")
    await client.delete("/configuracion/portada/imagen", headers=h_dra)
    await _subir(client, {"Authorization": "Bearer malo"}, _png())  # rechazada: no se audita

    async with session_factory() as s:
        filas = (await s.execute(select(AuditoriaUsuario).order_by(AuditoriaUsuario.fecha))).scalars().all()
    assert [f.accion for f in filas] == [
        "configuracion_actualizada",
        "imagen_portada_actualizada",
        "imagen_portada_eliminada",
    ]
    assert all(f.actor_id == usuarios["doctora"] for f in filas)
    texto = " ".join(f"{f.accion} {f.detalle or ''}" for f in filas)
    for prohibido in ("NombreConfidencial", "FraseConfidencial", "MarcaDePrueba"):
        assert prohibido not in texto
    assert all(f.detalle is None for f in filas)


async def test_rechazos_no_se_auditan(client, h_dra, session_factory):
    await _subir(client, h_dra, SVG, nombre="x.svg")
    await client.put("/configuracion/portada", headers=h_dra, json={"nombre": "n" * 500})
    async with session_factory() as s:
        assert (await s.execute(select(AuditoriaUsuario))).scalars().all() == []


async def test_el_campo_multipart_se_llama_archivo(client, h_dra):
    url = "/configuracion/portada/imagen"
    r = await client.put(url, headers=h_dra, files={"archivo": ("a.png", _png(), "image/png")})
    assert r.status_code == 200 and r.json()["tiene_imagen"] is True
    # Con otro nombre de campo la API no lo reconoce (422: falta "archivo").
    r = await client.put(url, headers=h_dra, files={"file": ("a.png", _png(), "image/png")})
    assert r.status_code == 422
    assert r.json()["detail"][0]["loc"] == ["body", "archivo"]
