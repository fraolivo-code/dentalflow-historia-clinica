# Odontograma mixto (15/10/2026): denticion del paciente, dientes deciduos (51-85) y sus reglas.
# Especificacion: docs/especificaciones/historia-clinica/especificacion-tecnica-odontograma-mixto.md

from datetime import date, timedelta

import pytest
import pytest_asyncio
from pydantic import ValidationError

from app import security
from app.enums import RolUsuario
from app.models import Usuario
from app.schemas.odontograma import PuenteFijoDienteCreate
from app.schemas.periodontograma import PeriodontogramaDienteResumenCreate


def _nac(anios: int) -> str:
    return (date.today() - timedelta(days=365 * anios + anios // 4 + 30)).isoformat()


@pytest_asyncio.fixture
async def usuarios(session_factory):
    ids = {}
    async with session_factory() as s:
        for nombre, rol in (("francisco", RolUsuario.dra), ("asistente", RolUsuario.asistente)):
            u = Usuario(nombre=nombre, rol=rol, password_hash="x", email=f"{nombre}@e.com")
            s.add(u)
            await s.flush()
            ids[nombre] = u.id
        await s.commit()
    return ids


@pytest.fixture
def h(usuarios):
    return {"Authorization": f"Bearer {security.crear_access_token(usuarios['francisco'], 'dra')}"}


@pytest.fixture
def h_asistente(usuarios):
    return {"Authorization": f"Bearer {security.crear_access_token(usuarios['asistente'], 'asistente')}"}


async def _paciente(client, h, anios=5, **extra):
    r = await client.post(
        "/pacientes",
        headers=h,
        json={
            "movil": "04141234567",
            "nombre_completo": "Paciente de prueba",
            "fecha_registro": "2026-10-05",
            "fecha_nacimiento": _nac(anios),
            **({"cedula": "V-12345678"} if anios >= 12 else {}),
            **extra,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _hallazgo(client, h, pid, diente, tipo, **extra):
    return await client.post(
        f"/pacientes/{pid}/dientes/{diente}/hallazgos",
        headers=h,
        json={"numero_diente": diente, "tipo_hallazgo": tipo, "fecha": "2026-10-01", **extra},
    )


# --------------------------------------------------------------------- denticion


@pytest.mark.parametrize("anios,esperada", [(5, "mixta"), (12, "mixta"), (13, "adulta"), (30, "adulta")])
async def test_denticion_sugerida_segun_la_edad(client, h, anios, esperada):
    assert (await _paciente(client, h, anios))["denticion"] == esperada


async def test_denticion_elegida_al_crear_manda_sobre_la_sugerida(client, h):
    assert (await _paciente(client, h, 30, denticion="mixta"))["denticion"] == "mixta"


async def test_cambiar_la_denticion_queda_en_el_historial_y_solo_acceso_total(client, h, h_asistente):
    p = await _paciente(client, h, 15)
    assert p["denticion"] == "adulta"
    url = f"/pacientes/{p['id']}"
    assert (await client.patch(url, headers=h_asistente, json={"denticion": "mixta"})).status_code == 403
    assert (await client.patch(url, headers=h, json={"denticion": None})).status_code == 422
    r = await client.patch(url, headers=h, json={"denticion": "mixta"})
    assert r.status_code == 200 and r.json()["denticion"] == "mixta"
    cambios = (await client.get(f"{url}/cambios", headers=h)).json()
    assert [(c["campo"], c["valor_anterior"], c["valor_nuevo"]) for c in cambios][-1] == ("denticion", "adulta", "mixta")


# ------------------------------------------------------------ dientes deciduos


async def test_los_deciduos_aceptan_hallazgos_comunes_y_los_propios(client, h):
    pid = (await _paciente(client, h))["id"]
    for diente, tipo, extra in (
        (54, "caries", {"superficie": "oclusal"}),
        (55, "pulpotomia", {}),
        (84, "sellante", {}),
        (53, "corona_ok", {}),
        (51, "diente_impactado", {}),  # un deciduo tambien puede quedar retenido
    ):
        r = await _hallazgo(client, h, pid, diente, tipo, **extra)
        assert r.status_code == 201, (diente, tipo, r.text)


@pytest.mark.parametrize(
    "tipo",
    [
        "implante", "carilla_ok", "carilla_defecto", "perno_ok", "perno_defecto", "conducto_ok",
        "conducto_ok_perno", "conducto_defecto", "conducto_perno_defecto", "conducto_indicado",
    ],
)
async def test_lo_que_no_aplica_en_un_deciduo_se_rechaza(client, h, tipo):
    pid = (await _paciente(client, h))["id"]
    r = await _hallazgo(client, h, pid, 54, tipo)
    assert r.status_code == 422 and "deciduo" in r.json()["detail"]


@pytest.mark.parametrize("tipo", ["exfoliado", "pulpotomia", "pulpectomia"])
async def test_lo_propio_de_deciduos_se_rechaza_en_permanentes(client, h, tipo):
    pid = (await _paciente(client, h, 30))["id"]
    r = await _hallazgo(client, h, pid, 14, tipo)
    assert r.status_code == 422 and "solo aplica en dientes deciduos" in r.json()["detail"]


async def test_exfoliado_cierra_lo_activo_y_queda_en_el_historial(client, h):
    pid = (await _paciente(client, h))["id"]
    await _hallazgo(client, h, pid, 54, "caries", superficie="oclusal")
    assert (await _hallazgo(client, h, pid, 54, "exfoliado")).status_code == 201
    activos = (await client.get(f"/pacientes/{pid}/odontograma", headers=h)).json()
    assert [a["tipo_hallazgo"] for a in activos] == ["exfoliado"]
    historial = (await client.get(f"/pacientes/{pid}/dientes/54/hallazgos", headers=h)).json()
    assert {x["tipo_hallazgo"] for x in historial} == {"caries", "exfoliado"}


async def test_pulpectomia_reemplaza_a_la_pulpotomia(client, h):
    pid = (await _paciente(client, h))["id"]
    await _hallazgo(client, h, pid, 74, "pulpotomia")
    await _hallazgo(client, h, pid, 74, "pulpectomia")
    activos = (await client.get(f"/pacientes/{pid}/odontograma", headers=h)).json()
    assert [a["tipo_hallazgo"] for a in activos] == ["pulpectomia"]


async def test_tratamiento_realizado_en_deciduo_extraccion_si_endodoncia_no(client, h):
    pid = (await _paciente(client, h))["id"]
    await _hallazgo(client, h, pid, 64, "caries", superficie="oclusal")
    url = f"/pacientes/{pid}/dientes/64/tratamiento-realizado"
    cuerpo = {"numero_diente": 64, "fecha": "2026-10-10"}
    r = await client.post(url, headers=h, json={**cuerpo, "tratamiento": "endodoncia"})
    assert r.status_code == 422
    r = await client.post(url, headers=h, json={**cuerpo, "tratamiento": "extraccion"})
    assert r.status_code == 201, r.text


async def test_los_numeros_fuera_del_catalogo_siguen_invalidos(client, h):
    pid = (await _paciente(client, h))["id"]
    for n in (56, 66, 50, 86, 19):
        assert (await _hallazgo(client, h, pid, n, "sano")).status_code in (400, 422), n


def test_puentes_y_periodontograma_no_aceptan_deciduos():
    with pytest.raises(ValidationError, match="deciduos"):
        PuenteFijoDienteCreate(numero_diente=54, rol="pilar", condicion_individual="sano")
    with pytest.raises(ValidationError, match="deciduos"):
        PeriodontogramaDienteResumenCreate(numero_diente=54, movilidad=0)
    PuenteFijoDienteCreate(numero_diente=14, rol="pilar", condicion_individual="sano")


# --------------------------------------------------------------------- remision


async def test_remision_es_una_observacion_de_la_dra_y_no_de_la_asistente(client, h, h_asistente):
    pid = (await _paciente(client, h))["id"]
    cuerpo = {"tipo": "remision", "fecha": "2026-10-15", "texto": "Ortodoncia: mantenedor de espacio colocado"}
    assert (await client.post(f"/pacientes/{pid}/observaciones", headers=h_asistente, json=cuerpo)).status_code == 422
    r = await client.post(f"/pacientes/{pid}/observaciones", headers=h, json=cuerpo)
    assert r.status_code == 201 and r.json()["tipo"] == "remision"


# ------------------------------------------------------------------- impresion

from types import SimpleNamespace as _NS  # noqa: E402

from app.services.odontograma_svg import MODO_BLANCO, MODO_COLOR, odontograma_svg  # noqa: E402


def _hallazgo_ns(numero, tipo, superficie=None):
    return _NS(numero_diente=numero, tipo_hallazgo=_NS(value=tipo), superficie=_NS(value=superficie) if superficie else None)


def test_el_dibujo_agrega_las_filas_de_deciduos_solo_cuando_corresponde():
    adulto = str(odontograma_svg([], [], [], {}, MODO_BLANCO))
    mixto = str(odontograma_svg([], [], [], {}, MODO_BLANCO, deciduos=True))
    assert 'data-diente="54"' not in adulto and 'data-diente="54"' in mixto
    assert mixto.count("data-diente=") == 52
    # automatico: aparecen si hay algo activo en un deciduo, nunca se oculta algo vigente
    auto = str(odontograma_svg([_hallazgo_ns(54, "caries", "oclusal")], [], [], {}, MODO_COLOR))
    assert 'data-diente="85"' in auto


def test_pulpotomia_pulpectomia_y_exfoliado_tienen_rotulo_en_el_dibujo():
    svg = str(odontograma_svg(
        [_hallazgo_ns(54, "pulpotomia"), _hallazgo_ns(64, "pulpectomia"), _hallazgo_ns(53, "exfoliado")],
        [], [], {}, MODO_COLOR,
    ))
    for rotulo in (">PT<", ">PX<", ">EXF<"):
        assert rotulo in svg, rotulo


async def test_hoja_en_blanco_mixta_trae_las_lineas_de_deciduos(client, h, monkeypatch):
    from app.services import pdf as servicio_pdf

    async def _render(plantilla, contexto):
        return servicio_pdf._plantillas.get_template(plantilla).render(**contexto).encode("utf-8")

    monkeypatch.setattr("app.routers.pdf.generar_pdf", _render)
    adulta = (await client.get("/pdf/odontograma-blanco", headers=h)).text
    mixta = (await client.get("/pdf/odontograma-blanco?denticion=mixta", headers=h)).text
    assert adulta.count('<td class="num">') == 32 and mixta.count('<td class="num">') == 52
    assert (await client.get("/pdf/odontograma-blanco?denticion=otra", headers=h)).status_code == 422
