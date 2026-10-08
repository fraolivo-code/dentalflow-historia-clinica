# Odontograma impreso (04/10/2026), Parte A: formulario de ingreso con
# odontograma en blanco, odontograma en blanco y odontograma actual del paciente
# (dibujo a color; lineas por diente y plan en gris).
# Especificacion: especificacion-tecnica-odontograma-impreso.md.
#
# WeasyPrint no se usa aqui: generar_pdf se sustituye por el render de la
# plantilla Jinja, y se verifica el HTML/SVG resultante.

from datetime import date as _date, timedelta as _timedelta

NAC_MENOR = (_date.today() - _timedelta(days=365 * 5)).isoformat()  # 5 anios: sin cedula obligatoria
import re
import uuid
from datetime import date

import pytest
import pytest_asyncio

from app import security
from app.enums import (
    EstadoGeneralPuente,
    RolDientePuente,
    RolUsuario,
    TipoHallazgo,
    TipoLesionApical,
)
from app.models import OdontogramaLesionApical, PuenteFijo, PuenteFijoDiente, Usuario
from app.routers import historia_clinica
from app.services import odontograma_impreso as impreso
from app.services import pdf as servicio_pdf
from app.services.odontograma_svg import MODO_BLANCO, MODO_GRIS, odontograma_svg

COLOR = re.compile(r"#[0-9a-fA-F]{6}\b")


@pytest.fixture(autouse=True)
def sin_weasyprint(monkeypatch):
    """El 'PDF' de estos tests es el HTML renderizado de la plantilla."""

    async def _render(plantilla: str, contexto: dict) -> bytes:
        return servicio_pdf._plantillas.get_template(plantilla).render(**contexto).encode("utf-8")

    monkeypatch.setattr("app.routers.pdf.generar_pdf", _render)
    monkeypatch.setattr("app.routers.historia_clinica.generar_pdf", _render)

    async def _sin_raices(session):  # diente_anatomia usa ARRAY: no existe en SQLite
        return {}

    monkeypatch.setattr(impreso, "raices_por_diente", _sin_raices)


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


def _colores(html: str) -> set[str]:
    return {c.lower() for c in COLOR.findall(html)}


def _es_gris_o_negro(color: str) -> bool:
    return color[1:3] == color[3:5] == color[5:7]


def _svg(html: str) -> str:
    return re.search(r"<svg.*?</svg>", html, re.S).group(0)


def _linea(html: str, diente: int) -> str:
    """Texto (gris) de la linea de un diente en la hoja."""
    m = re.search(rf'<td class="num">{diente}</td><td class="texto">(.*?)</td>', html, re.S)
    assert m, f"no hay linea para el diente {diente}"
    return m.group(1)


def _plan(html: str) -> list[str]:
    bloque = re.search(r'<div class="odo-plan">(.*?)</div>\s*$', html, re.S) or re.search(
        r'<div class="odo-plan">(.*)', html, re.S
    )
    return re.findall(r'<div class="renglon-plan">(.*?)</div>', bloque.group(1), re.S)


async def _paciente(client, h, nombre="Paciente Gris"):
    r = await client.post(
        "/pacientes",
        headers=h,
        json={"movil": "04141234567", "nombre_completo": nombre, "fecha_registro": "2026-10-05", "fecha_nacimiento": NAC_MENOR,
              "fecha_primera_consulta_real": "2012-04-01"},
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _hallazgo(client, h, pid, diente, tipo, superficie=None, fecha="2026-09-10"):
    r = await client.post(
        f"/pacientes/{pid}/dientes/{diente}/hallazgos",
        headers=h,
        json={"numero_diente": diente, "tipo_hallazgo": tipo, "superficie": superficie, "fecha": fecha},
    )
    assert r.status_code == 201, r.text
    return r.json()


@pytest_asyncio.fixture
async def paciente_con_datos(client, h_dra, usuarios, session_factory):
    """Hallazgos activos y uno resuelto, una lesion apical, un puente y tratamientos."""
    paciente = await _paciente(client, h_dra)
    pid = paciente["id"]
    await _hallazgo(client, h_dra, pid, 16, "caries", "oclusal")
    await _hallazgo(client, h_dra, pid, 26, "corona_ok")
    viejo = await _hallazgo(client, h_dra, pid, 36, "conducto_indicado")
    r = await client.patch(
        f"/pacientes/{pid}/hallazgos/{viejo['id']}/resolver", headers=h_dra, json={"fecha": "2026-09-20"}
    )
    assert r.status_code == 200
    async with session_factory() as s:
        s.add(
            OdontogramaLesionApical(
                paciente_id=uuid.UUID(pid), numero_diente=16, raiz="Mesiovestibular",
                tipo=TipoLesionApical.periapical, fecha=date(2026, 9, 11), resuelto=False,
                creado_por=usuarios["doctora"],
            )
        )
        puente = PuenteFijo(
            paciente_id=uuid.UUID(pid), estado_general=EstadoGeneralPuente.ok,
            fecha=date(2026, 9, 1), creado_por=usuarios["doctora"],
        )
        s.add(puente)
        await s.flush()
        for n, rol, cond in ((44, RolDientePuente.pilar, TipoHallazgo.sano),
                             (45, RolDientePuente.pontico, TipoHallazgo.ausente),
                             (46, RolDientePuente.pilar, TipoHallazgo.sano)):
            s.add(PuenteFijoDiente(puente_id=puente.id, numero_diente=n, rol=rol,
                                   condicion_individual=cond, creado_por=usuarios["doctora"]))
        await s.commit()
    prof = (await client.post("/profesionales-tratantes", headers=h_dra, json={"nombre": "Dra. X"})).json()["id"]
    for tipo, estado, dientes in (
        ("endodoncia", "en_curso", [11, 12]),
        ("ortodoncia", "indicado", []),
        ("limpieza", "completado", [21]),
        ("implante", "suspendido", [31]),
    ):
        r = await client.post(
            f"/pacientes/{pid}/tratamientos", headers=h_dra,
            json={"tipo": tipo, "estado": estado, "fecha_inicio": "2026-09-01",
                  "profesional_tratante_id": prof, "dientes": dientes},
        )
        assert r.status_code == 201, r.text
    return paciente


# ============================================================ A.1 dibujo


def test_modo_blanco_no_dibuja_hallazgos_aunque_se_los_pasen():
    from types import SimpleNamespace as NS

    h = NS(numero_diente=16, tipo_hallazgo=TipoHallazgo.caries, superficie=NS(value="oclusal"))
    con = odontograma_svg([h], [], [], {}, MODO_BLANCO)
    sin = odontograma_svg([], [], [], {}, MODO_BLANCO)
    assert con == sin


def test_modo_blanco_y_gris_no_tienen_color():
    from types import SimpleNamespace as NS

    h = NS(numero_diente=16, tipo_hallazgo=TipoHallazgo.caries, superficie=NS(value="oclusal"))
    c = NS(numero_diente=26, tipo_hallazgo=TipoHallazgo.corona_defecto, superficie=None)
    e = NS(numero_diente=11, tipo_hallazgo=TipoHallazgo.conducto_defecto, superficie=None)
    for svg in (odontograma_svg([], [], [], {}, MODO_BLANCO), odontograma_svg([h, c, e], [], [], {}, MODO_GRIS)):
        colores = _colores(svg)
        assert colores and all(_es_gris_o_negro(x) for x in colores), colores
        assert "#1565c0" not in svg.lower() and "#c62828" not in svg.lower()


def test_modo_gris_dibuja_lo_activo_en_gris_y_el_color_sigue_igual():
    from types import SimpleNamespace as NS

    h = NS(numero_diente=16, tipo_hallazgo=TipoHallazgo.caries, superficie=NS(value="oclusal"))
    gris = odontograma_svg([h], [], [], {}, MODO_GRIS)
    blanco = odontograma_svg([], [], [], {}, MODO_BLANCO)
    color = odontograma_svg([h], [], [], {})
    assert gris != blanco and "#a6a6a6" in gris  # caries (rojo en pantalla) -> gris claro
    assert "#c62828" in color  # el modo de pantalla no cambio


def test_modo_desconocido_falla():
    with pytest.raises(ValueError):
        odontograma_svg([], [], [], {}, "sepia")


# ============================================ A.2 lineas por diente (unidad)


def test_lineas_por_diente_orden_del_papel_y_textos():
    sin = impreso.lineas_por_diente()
    assert [n for n, _ in sin["superior"]] == [18, 17, 16, 15, 14, 13, 12, 11, 21, 22, 23, 24, 25, 26, 27, 28]
    assert [n for n, _ in sin["inferior"]] == [48, 47, 46, 45, 44, 43, 42, 41, 31, 32, 33, 34, 35, 36, 37, 38]
    assert all(texto == "" for _, texto in sin["superior"] + sin["inferior"])
    con = impreso.lineas_por_diente({16: ["Caries (oclusal)", "Lesión apical (mesiovestibular)"]})
    assert dict(con["superior"])[16] == "Caries (oclusal) · Lesión apical (mesiovestibular)"
    assert dict(con["superior"])[17] == ""


# ===================================================== A.3 endpoints en blanco


async def test_formulario_de_ingreso_incluye_odontograma_en_blanco_y_membrete_del_consultorio(
    client, h_dra, h_asistente, monkeypatch
):
    monkeypatch.setenv("NOMBRE_PRODUCTO", "Producto Prueba")
    # La asistente (sin profesional vinculado) lo imprime; sin configuracion usa NOMBRE_PRODUCTO.
    r = await client.get("/pdf/formulario-ingreso", headers=h_asistente)
    assert r.status_code == 200
    assert "inline" in r.headers["content-disposition"]
    html = r.text
    assert "Producto Prueba" in html and "colegiatura" not in html
    assert "Datos personales" in html and "Motivo de consulta" in html  # pagina 1 como hoy
    assert 'class="pagina-odontograma"' in html and "Plan de tratamiento" in html  # pagina 2
    assert html.count('<td class="num">') == 32
    assert all(_linea(html, n) == "" for n in (18, 11, 41, 38))
    assert all(_es_gris_o_negro(x) for x in _colores(_svg(html)))

    # Con la configuracion de la portada: nombre y frase.
    await client.put("/configuracion/portada", headers=h_dra,
                     json={"nombre": "Od. Leonor Granados", "frase": "Sonríe desde adentro"})
    html = (await client.get("/pdf/formulario-ingreso", headers=h_asistente)).text
    assert "Od. Leonor Granados" in html and "Sonríe desde adentro" in html
    assert "Producto Prueba" not in html


async def test_odontograma_en_blanco(client, h_asistente, h_dra):
    for h in (h_asistente, h_dra):
        r = await client.get("/pdf/odontograma-blanco", headers=h)
        assert r.status_code == 200
        assert 'filename="odontograma-blanco.pdf"' in r.headers["content-disposition"]
        html = r.text
        assert "N.° de historia:" in html and "Paciente:" in html and "Fecha:" in html
        assert html.count('<td class="num">') == 32
        assert all(_linea(html, n) == "" for n in range(1, 50) if f'<td class="num">{n}</td>' in html)
        assert "Las líneas en gris muestran lo ya registrado" not in html  # nota solo del actual
        assert all(_es_gris_o_negro(x) for x in _colores(_svg(html)))
        assert "--acento: #000" in html  # sin colores de marca
        assert _plan(html) == ["", "", "", ""]  # lineas libres, sin tratamientos


async def test_periodontograma_en_blanco(client, h_asistente, h_dra):
    for h in (h_asistente, h_dra):
        r = await client.get("/pdf/periodontograma-blanco", headers=h)
        assert r.status_code == 200
        assert 'filename="periodontograma-blanco.pdf"' in r.headers["content-disposition"]
        html = r.text
        assert "size: A4 landscape" in html  # una hoja horizontal
        assert "N.° de historia:" in html and "Paciente:" in html and "Fecha:" in html
        # los 32 dientes, en orden de boca, en cada arco
        for n in (18, 11, 21, 28, 48, 41, 31, 38):
            assert f'colspan="3">{n}</td>' in html
        assert html.count('colspan="3">') >= 32 + 4 * 16  # numeros + movilidad y furcacion
        assert "Arco superior" in html and "Arco inferior" in html
        assert "Palatino" in html and "Lingual" in html
        assert "MG (mm)" in html and "PS (mm)" in html and "NI (mm)" in html
        assert "--acento: #000" in html  # sin colores de marca


async def test_los_impresos_en_blanco_piden_sesion(client):
    assert (await client.get("/pdf/formulario-ingreso")).status_code == 401
    assert (await client.get("/pdf/odontograma-blanco")).status_code == 401
    assert (await client.get("/pdf/periodontograma-blanco")).status_code == 401


# ===================================================== A.3 odontograma actual


async def test_odontograma_actual_solo_acceso_total(client, h_asistente, h_dra):
    paciente = await _paciente(client, h_dra)
    url = f"/pacientes/{paciente['id']}/pdf/odontograma-actual"
    assert (await client.get(url, headers=h_asistente)).status_code == 403
    assert (await client.get(url)).status_code == 401
    assert (await client.get(url, headers=h_dra)).status_code == 200
    assert (await client.get(f"/pacientes/{uuid.uuid4()}/pdf/odontograma-actual", headers=h_dra)).status_code == 404


async def test_odontograma_actual_encabezado_y_lineas_en_gris(client, h_dra, paciente_con_datos):
    paciente = paciente_con_datos
    r = await client.get(f"/pacientes/{paciente['id']}/pdf/odontograma-actual", headers=h_dra)
    assert r.status_code == 200
    assert "inline" in r.headers["content-disposition"]
    html = r.text
    assert "Paciente Gris" in html
    assert f"{paciente['numero_historia']} · Paciente desde 2012" in html
    assert "Fecha de impresión" in html
    assert "Las líneas en gris muestran lo ya registrado" in html
    assert "DentalFlow" in html or "membrete-nombre" in html  # membrete del consultorio, no del profesional
    assert "colegiatura" not in html

    # Hallazgos y lesiones activos, con el texto de la historia completa.
    assert _linea(html, 16) == "Caries (oclusal) · Lesión apical (mesiovestibular)"
    assert _linea(html, 26) == "Corona en buen estado"
    # Puente activo: texto por diente.
    assert _linea(html, 44).startswith("Puente 46-45-44") or _linea(html, 44).startswith("Puente 44-45-46")
    assert "póntico" in _linea(html, 45) and "pilar" in _linea(html, 44)
    # Resuelto: no aparece. Diente sin nada: libre.
    assert _linea(html, 36) == ""
    assert _linea(html, 18) == ""
    assert "Conducto indicado" not in html


async def test_odontograma_actual_dibuja_a_color_y_las_lineas_van_en_gris(client, h_dra, paciente_con_datos):
    html = (await client.get(f"/pacientes/{paciente_con_datos['id']}/pdf/odontograma-actual", headers=h_dra)).text
    # El dibujo es el mismo que el de la historia completa (modo color): la caries
    # es roja y no hay sustitutos grises.
    svg = _svg(html)
    assert "#c62828" in svg and "#1565c0" in svg
    assert "#a6a6a6" not in svg and "#8c8c8c" not in svg
    # El texto de la hoja (datos, lineas por diente, plan) no usa color; los colores
    # de marca de la base quedan pisados por el documento.
    fuera_del_dibujo = html[html.index('<section class="cuerpo">'):].replace(svg, "")
    assert all(_es_gris_o_negro(x) for x in _colores(fuera_del_dibujo))
    assert "--acento: #000" in html and "--primario: #000" in html
    assert 'class="texto"' in html and "color: #7a7a7a" in html  # las lineas en gris
    # La nota de la hoja.
    assert (
        "Las líneas en gris muestran lo ya registrado. "
        "Anote cada hallazgo nuevo también en la línea de su diente."
    ) in html
    assert "impreso en gris" not in html


async def test_odontograma_actual_plan_con_tratamientos_activos(client, h_dra, paciente_con_datos):
    html = (await client.get(f"/pacientes/{paciente_con_datos['id']}/pdf/odontograma-actual", headers=h_dra)).text
    plan = _plan(html)
    assert plan[0] == "endodoncia — dientes 12, 11 (En curso)" or plan[0] == "endodoncia — dientes 11, 12 (En curso)"
    assert plan[1] == "ortodoncia (Indicado)"
    assert len(plan) >= 4 and plan[2] == ""  # lineas libres debajo
    assert "limpieza" not in html and "suspendido" not in html.lower()  # completados/suspendidos no van


async def test_odontograma_actual_de_paciente_sin_nada(client, h_dra):
    paciente = await _paciente(client, h_dra, "Paciente Vacio")
    html = (await client.get(f"/pacientes/{paciente['id']}/pdf/odontograma-actual", headers=h_dra)).text
    assert html.count('<td class="num">') == 32
    assert all(_linea(html, n) == "" for n in (18, 16, 41))
    assert _plan(html) == ["", "", "", ""]


async def test_membrete_del_odontograma_actual_sale_de_la_configuracion(client, h_dra):
    await client.put("/configuracion/portada", headers=h_dra, json={"nombre": "Consultorio Sol", "frase": None})
    paciente = await _paciente(client, h_dra)
    html = (await client.get(f"/pacientes/{paciente['id']}/pdf/odontograma-actual", headers=h_dra)).text
    assert "Consultorio Sol" in html


# ------------------------------------------- la historia completa no cambio


async def test_historia_completa_sigue_igual_tras_compartir_el_codigo(
    client, h_dra, paciente_con_datos, session_factory
):
    pid = uuid.UUID(paciente_con_datos["id"])
    async with session_factory() as s:
        odo = await historia_clinica._odontograma(s, pid)
    leyenda = dict(odo["leyenda"])
    assert leyenda[16] == ["Caries (oclusal)", "Lesión apical (mesiovestibular)"]
    assert leyenda[26] == ["Corona en buen estado"]
    assert any("Puente 46-45-44" in t or "Puente 44-45-46" in t for t in leyenda[45])
    assert [(r["dientes"], r["descripcion"]) for r in odo["resueltos"]] == [("36", "Conducto indicado")]
    # La historia completa sigue a color.
    assert "#c62828" in odo["svg"] or "#1565c0" in odo["svg"]
