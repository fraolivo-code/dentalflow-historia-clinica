# Odontograma, criterio de la Dra. (18/10/2026): superficies por diente, nombres y gingivitis.
# Especificacion: docs/proceso-trabajo-caso-334.md (sec. 13, punto 11) y el encargo del 18/10/2026.

import pytest

from app.enums import GRUPO_CONDICION, SuperficieDental, TipoHallazgo
from app.services import etiquetas
from tests.test_odontograma_anatomico import _diente, _dibujo, _h, _tag

OCLUSAL = SuperficieDental.oclusal
PALATINO_LINGUAL = SuperficieDental.palatino_lingual


@pytest.mark.parametrize("diente", [11, 12, 13, 22, 23, 33, 43, 53, 63, 73, 83, 52])
def test_anteriores_de_canino_a_canino_dicen_incisal_nunca_oclusal(diente):
    assert etiquetas.etiqueta_superficie(OCLUSAL, [diente]) == "incisal"


@pytest.mark.parametrize("diente", [14, 16, 26, 36, 46, 18, 54, 55, 74, 85])
def test_posteriores_dicen_oclusal_nunca_incisal(diente):
    assert etiquetas.etiqueta_superficie(OCLUSAL, [diente]) == "oclusal"


def test_varios_dientes_de_grupos_distintos_muestran_los_dos_nombres():
    assert etiquetas.etiqueta_superficie(OCLUSAL, [22, 36]) == "oclusal / incisal"
    assert etiquetas.etiqueta_superficie(OCLUSAL, []) == "oclusal"


@pytest.mark.parametrize("diente, esperada", [(22, "palatina"), (11, "palatina"), (55, "palatina"),
                                              (36, "lingual"), (33, "lingual"), (74, "lingual")])
def test_superiores_palatina_e_inferiores_lingual(diente, esperada):
    assert etiquetas.etiqueta_superficie(PALATINO_LINGUAL, [diente]) == esperada


def test_el_hallazgo_con_superficie_usa_el_nombre_segun_el_diente():
    assert etiquetas.etiqueta_hallazgo(TipoHallazgo.caries, OCLUSAL, 22) == "Caries (incisal)"
    assert etiquetas.etiqueta_hallazgo(TipoHallazgo.caries, OCLUSAL, 36) == "Caries (oclusal)"
    assert etiquetas.etiqueta_hallazgo(TipoHallazgo.caries, PALATINO_LINGUAL, 22) == "Caries (palatina)"
    assert etiquetas.etiqueta_hallazgo(TipoHallazgo.caries, PALATINO_LINGUAL, 36) == "Caries (lingual)"


def test_nombres_en_los_documentos():
    assert etiquetas.HALLAZGO[TipoHallazgo.requiere_periodontal] == "Periodontitis (PER)"
    assert etiquetas.HALLAZGO[TipoHallazgo.gingivitis] == "Gingivitis (GING)"
    assert etiquetas.HALLAZGO[TipoHallazgo.sellante] == "SELL Aplicado"
    assert etiquetas.HALLAZGO[TipoHallazgo.spp].startswith("Superficie prepatogénica")


def test_todo_tipo_de_hallazgo_tiene_nombre_en_los_documentos():
    assert set(etiquetas.HALLAZGO) == set(TipoHallazgo)


def test_gingivitis_es_una_condicion_compatible_con_todo():
    assert TipoHallazgo.gingivitis in GRUPO_CONDICION


# --- Implante rehabilitado / no rehabilitado --------------------------------------------------------

from app.services.odontograma_svg import CORONA, ROJO  # noqa: E402
from tests.test_odontograma_anatomico import AZUL, _con, _vista  # noqa: E402


def _implante(numero, rehabilitado):
    h = _h(numero, "implante")
    h.rehabilitado = rehabilitado
    return h


def _coronas(svg, numero, vista):
    return _con(_vista(svg, numero, vista), fill=CORONA)


def test_implante_rehabilitado_se_dibuja_con_tornillo_y_corona():
    svg = _dibujo([_implante(46, True)])
    assert _con(_vista(svg, 46, "vestibular"), "line", stroke=AZUL)   # tornillo
    assert _coronas(svg, 46, "vestibular")                              # corona
    assert _coronas(svg, 46, "oclusal")


def test_implante_sin_dato_de_rehabilitado_se_dibuja_como_rehabilitado():
    # Los implantes guardados antes del cambio no traen el dato: se muestran como siempre.
    svg = _dibujo([_h(46, "implante")])
    assert _coronas(svg, 46, "vestibular") and _coronas(svg, 46, "oclusal")


def test_implante_no_rehabilitado_solo_tornillo_sin_corona():
    svg = _dibujo([_implante(46, False)])
    assert _con(_vista(svg, 46, "vestibular"), "line", stroke=AZUL)   # el tornillo se mantiene
    assert not _coronas(svg, 46, "vestibular")
    assert not _coronas(svg, 46, "oclusal")


def test_periimplantitis_se_sigue_dibujando_en_un_implante_no_rehabilitado():
    from tests.test_odontograma_anatomico import _lesion
    from app.enums import TipoLesionApical

    svg = _dibujo([_implante(46, False)], [_lesion(46, "", TipoLesionApical.periimplantitis)])
    assert _con(_vista(svg, 46, "vestibular"), "circle", fill=ROJO)

