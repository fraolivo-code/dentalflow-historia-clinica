"""Enlaza a la visita de un dia lo que se cargo ese dia sin visita (bitacora y hallazgos del odontograma).

Hasta el 15/10/2026 la pantalla no enlazaba «Tratamiento realizado» a la visita; desde entonces lo
hace sola. Este procedimiento arregla lo ya cargado. No borra nada ni cambia fechas.

ANTES de ejecutarlo de verdad:
  1. Corra el respaldo («Run now» en dentalflow-backup-cron) y espere el correo "Backup OK".
  2. Corra el ENSAYO (no cambia nada) y lea que se va a enlazar.
  3. La visita de ese dia debe existir y ser una sola.

Uso (desde la carpeta backend, o dentro del contenedor de la API en Railway):

  Ensayo, no cambia nada:
    python scripts/enlazar_visita.py --historia 000317 --fecha 2019-04-23

  Real:
    python scripts/enlazar_visita.py --historia 000317 --fecha 2019-04-23 --ejecutar
"""

import argparse
import asyncio
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import async_session  # noqa: E402
from app.services import borrado_paciente, enlazar_visita  # noqa: E402


async def principal(args: argparse.Namespace) -> int:
    fecha = date.fromisoformat(args.fecha)
    async with async_session() as session:
        paciente = await borrado_paciente.buscar_por_historia(session, args.historia)
        if paciente is None:
            print(f"No existe la historia {args.historia}. No se cambio nada.")
            return 1
        print(f"Paciente: historia {paciente.numero_historia} — {paciente.nombre_completo}")
        try:
            visita = await enlazar_visita.visita_del_dia(session, paciente.id, fecha)
        except enlazar_visita.SinVisitaUnica as error:
            print(error)
            return 1
        sueltos = await enlazar_visita.sueltos_del_dia(session, paciente.id, fecha)
        print(f"Visita del {fecha.isoformat()}: {visita.id} (tipo: {visita.tipo.value if visita.tipo else 'sin tipo'})")
        print(f"Entradas de bitacora sin visita ese dia: {len(sueltos['bitacora'])}")
        for e in sueltos["bitacora"]:
            print(f"  - diente(s) {e.numero_diente or ''}: {e.descripcion[:90]}")
        print(f"Hallazgos del odontograma sin visita ese dia: {len(sueltos['hallazgos'])}")
        for h in sueltos["hallazgos"]:
            print(f"  - diente {h.numero_diente}: {h.tipo_hallazgo.value}")
        if not args.ejecutar:
            print("\nENSAYO: no se cambio nada. Agregue --ejecutar para enlazar.")
            return 0
        hecho = await enlazar_visita.enlazar(session, paciente.id, fecha)
        print(f"\nListo: {hecho['bitacora']} entradas de bitacora y {hecho['hallazgos']} hallazgos enlazados.")
        return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--historia", required=True, help="Numero de historia (ej. 000317 o 317)")
    parser.add_argument("--fecha", required=True, help="Fecha AAAA-MM-DD de lo que se enlaza")
    parser.add_argument("--ejecutar", action="store_true", help="Enlaza de verdad (sin esto es solo un ensayo)")
    sys.exit(asyncio.run(principal(parser.parse_args())))
