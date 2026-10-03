import pytest

from app.services.vinculacion import evaluar_coincidencia, extraer_nombre_y_apellido


@pytest.mark.parametrize(
    "texto, esperado",
    [
        ("María", ("maria", None)),
        ("  MARÍA   Pérez ", ("maria", "perez")),
        ("soy María", ("maria", None)),
        ("Me llamo María Pérez", ("maria", "perez")),
        ("es para mi hijo Pedro", ("pedro", None)),
        ("Hola, buenas tardes, soy Pedro Díaz!", ("pedro", "diaz")),
        ("", (None, None)),
        ("soy", (None, None)),
    ],
)
def test_extraccion(texto, esperado):
    assert extraer_nombre_y_apellido(texto) == esperado


REG = ["María José Pérez González"]


def test_coincide_por_nombre_con_tildes_y_mayusculas_distintas():
    assert evaluar_coincidencia(REG, "maria") == {"coincide": True, "nombre_saludo": "María"}
    assert evaluar_coincidencia(REG, "MARÍA") == {"coincide": True, "nombre_saludo": "María"}


def test_coincide_por_nombre_y_apellido():
    assert evaluar_coincidencia(REG, "María Pérez")["coincide"] is True


def test_apellido_que_no_coincide():
    assert evaluar_coincidencia(REG, "María Rojas") == {"coincide": False}


def test_apodo_no_coincide():
    assert evaluar_coincidencia(REG, "Mari") == {"coincide": False}


def test_frases_previas():
    assert evaluar_coincidencia(REG, "soy María")["coincide"] is True
    assert evaluar_coincidencia(["Pedro Díaz"], "es para mi hijo Pedro") == {
        "coincide": True,
        "nombre_saludo": "Pedro",
    }


def test_dos_candidatos_mismo_nombre_pide_apellido_y_desempata():
    dos = ["Pedro Díaz Ruiz", "Pedro Pérez Gil"]
    assert evaluar_coincidencia(dos, "Pedro") == {"coincide": False, "pedir_apellido": True}
    assert evaluar_coincidencia(dos, "Pedro Pérez") == {"coincide": True, "nombre_saludo": "Pedro"}


def test_apellido_dado_y_aun_ambiguo_no_pide_otra_vez():
    dos = ["Pedro Pérez Ruiz", "Pedro Pérez Gil"]
    assert evaluar_coincidencia(dos, "Pedro Pérez") == {"coincide": False}


def test_sin_candidatos_o_texto_vacio():
    assert evaluar_coincidencia([], "María") == {"coincide": False}
    assert evaluar_coincidencia(REG, "") == {"coincide": False}


def test_nunca_devuelve_otro_nombre():
    assert evaluar_coincidencia(["Ana Gil", "Luis Gil"], "Carlos") == {"coincide": False}
