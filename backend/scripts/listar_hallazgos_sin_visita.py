"""Informe de SOLO LECTURA: hallazgos del odontograma que quedaron como un dia aparte, sin visita.

Cuando la fecha del odontograma era «hoy» por defecto, lo marcado sin una visita ese dia quedaba suelto
(visita_id vacio) y aparecia como otro dia en «Historia por visita». Este informe los lista para decidir,
caso por caso con la Dra., a que visita pertenecen. NO modifica nada.

Uso (desde la carpeta backend, o dentro del contenedor de la API en Railway):

    python scripts/listar_hallazgos_sin_visita.py
    python scripts/listar_hallazgos_sin_visita.py --historia 000334
    python scripts/listar_hallazgos_sin_visita.py --solo-fecha-de-captura   # los marcados con la fecha del dia en que se cargaron

Por cada hallazgo muestra: historia, diente, hallazgo, fecha, dia de captura y la visita mas cercana por
fecha. Para corregirlos, la API todavia no tiene un cambio de fecha/visita de un hallazgo (pendiente, ver
docs/proceso-trabajo-caso-334.md): hoy solo se puede resolver o, en historias en carga, eliminar y volver a
marcar con la fecha de la visita.
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.db import async_session  # noqa: E402
from app.models.common import a_utc  # noqa: E402
from app.models.odontograma import OdontogramaHallazgo  # noqa: E402
from app.models.paciente import Paciente  # noqa: E402
from app.models.visita import Visita  # noqa: E402
from app.services import etiquetas  # noqa: E402


async def principal(args: argparse.Namespace) -> int:
    async with async_session() as session:
        consulta = (
            select(OdontogramaHallazgo, Paciente)
            .join(Paciente, Paciente.id == OdontogramaHallazgo.paciente_id)
            .where(OdontogramaHallazgo.visita_id.is_(None))
            .order_by(Paciente.numero_historia, OdontogramaHallazgo.fecha, OdontogramaHallazgo.numero_diente)
        )
        if args.historia:
            consulta = consulta.where(Paciente.numero_historia == args.historia)
        filas = (await session.execute(consulta)).all()

        visitas: dict = {}
        total = 0
        for h, paciente in filas:
            captura = a_utc(h.creado_en).date()
            if args.solo_fecha_de_captura and h.fecha != captura:
                continue
            if paciente.id not in visitas:
                visitas[paciente.id] = sorted(
                    (await session.execute(select(Visita.fecha).where(Visita.paciente_id == paciente.id))).scalars()
                )
            cercana = min(visitas[paciente.id], key=lambda f: abs((f - h.fecha).days), default=None)
            print(
                f"{paciente.numero_historia} · diente {h.numero_diente} · "
                f"{etiquetas.etiqueta_hallazgo(h.tipo_hallazgo, h.superficie, h.numero_diente)} · "
                f"fecha {h.fecha} · capturado {captura} · visita mas cercana: {cercana or 'ninguna'}"
            )
            total += 1
        print(f"\n{total} hallazgo(s) sin visita. No se modifico nada.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--historia", help="numero de historia, ej. 000334")
    parser.add_argument("--solo-fecha-de-captura", action="store_true")
    sys.exit(asyncio.run(principal(parser.parse_args())))
