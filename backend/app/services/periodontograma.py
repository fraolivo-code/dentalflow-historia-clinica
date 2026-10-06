# app/services/periodontograma.py — Calculo del periodontograma.

# Convencion de la Dra. (Universidad de Berna / perio-tools.com, 05/10/2026):
# el margen gingival (MG) se anota en NEGATIVO cuando hay recesion.
NIVEL_INSERCION_SQL = "nivel_insercion = profundidad_sondaje - margen_gingival"


def calcular_nivel_insercion(margen_gingival: int, profundidad_sondaje: int) -> int:
    """NI = profundidad de sondaje - margen gingival. Unico lugar donde se calcula."""
    return profundidad_sondaje - margen_gingival
