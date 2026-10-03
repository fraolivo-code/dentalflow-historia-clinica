import pytest

from app.services.movil import normalizar_movil


@pytest.mark.parametrize(
    "texto, esperado",
    [
        ("0414-1234567", "584141234567"),  # 11 digitos con 0
        ("04141234567", "584141234567"),
        ("(0414) 123 45 67", "584141234567"),
        ("4141234567", "584141234567"),  # 10 digitos
        ("414 123.45.67", "584141234567"),
        ("584141234567", "584141234567"),  # 12 con 58
        ("+58 414-123-4567", "584141234567"),
        ("+58 (414) 1234567", "584141234567"),
        ("02121234567", "582121234567"),  # fijo
    ],
)
def test_formatos_venezolanos(texto, esperado):
    assert normalizar_movil(texto) == esperado


@pytest.mark.parametrize(
    "texto",
    [
        None,
        "",
        "   ",
        "abc",
        "041412345",  # incompleto (9)
        "414123456",  # incompleto (9)
        "58414123456",  # 11 digitos que no empiezan con 0
        "5841412345678",  # 13 digitos
        "+1 305 555 1234",  # extranjero (11, empieza con 1)
        "+34 612 345 678",  # extranjero (11)
        "+57 300 123 4567",  # extranjero (12, empieza con 57)
        "12345678901234",
    ],
)
def test_otros_casos_devuelven_none(texto):
    assert normalizar_movil(texto) is None
