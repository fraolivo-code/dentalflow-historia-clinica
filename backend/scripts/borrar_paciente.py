"""Borra UN paciente de prueba con todo lo que depende de el (visitas, bitacora, odontograma...).

La aplicacion no borra pacientes: esto es un procedimiento aparte, para quitar de produccion
los pacientes de PRUEBA, y lo ejecuta Francisco, nunca la Dra.

ANTES de ejecutarlo de verdad:
  1. Corra el respaldo («Run now» en dentalflow-backup-cron) y espere el correo "Backup OK".
  2. Corra el ENSAYO (no borra nada) y lea que se va a borrar.

Uso (desde la carpeta backend, o dentro del contenedor de la API en Railway):

  Ensayo, no borra:
    python scripts/borrar_paciente.py --historia 000434

  Borrado real:
    python scripts/borrar_paciente.py --historia 000434 --ejecutar --confirmo "BORRAR 000434"

Seguridad: se niega a borrar si el nombre del paciente no contiene la palabra "prueba"
(sin importar mayusculas). Si de verdad hay que borrar otro paciente, agregue --forzar-no-prueba.
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import async_session  # noqa: E402
from app.services import borrado_paciente  # noqa: E402


def _tabla(cuentas: dict[str, int]) -> str:
    return "\n".join(f"  {nombre:<32} {n}" for nombre, n in sorted(cuentas.items()))


async def principal(args: argparse.Namespace) -> int:
    async with async_session() as session:
        paciente = await borrado_paciente.buscar_por_historia(session, args.historia)
        if paciente is None:
            print(f"No existe un paciente con la historia {args.historia}. No se hizo nada.")
            return 1
        es_prueba = "prueba" in paciente.nombre_completo.lower()
        print(f"Paciente: historia {paciente.numero_historia} — {paciente.nombre_completo}")
        if not es_prueba and not args.forzar_no_prueba:
            print(
                'El nombre no contiene "prueba": no se borra. '
                "Si de verdad hay que borrarlo, repita con --forzar-no-prueba."
            )
            return 1

        cuentas = await borrado_paciente.contar(session, paciente.id)
        print("Se borrarian estas filas:")
        print(_tabla(cuentas))

        if not args.ejecutar:
            print("\nENSAYO: no se borro nada. Para borrar agregue: --ejecutar --confirmo "
                  f'"BORRAR {paciente.numero_historia}"')
            return 0
        esperado = f"BORRAR {paciente.numero_historia}"
        if args.confirmo != esperado:
            print(f'\nFalta la confirmacion exacta: --confirmo "{esperado}". No se borro nada.')
            return 1

        borradas = await borrado_paciente.borrar(session, paciente.id)
        print("\nBORRADO. Filas borradas:")
        print(_tabla(borradas))
        if await borrado_paciente.buscar_por_historia(session, args.historia) is not None:
            print("ATENCION: el paciente sigue existiendo.")
            return 2
        return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--historia", required=True, help="Numero de historia (ej. 000434 o 434)")
    parser.add_argument("--ejecutar", action="store_true", help="Borra de verdad (sin esto es solo un ensayo)")
    parser.add_argument("--confirmo", default="", help='Texto exacto: "BORRAR <numero de historia>"')
    parser.add_argument("--forzar-no-prueba", action="store_true", help="Permite borrar un paciente sin 'prueba' en el nombre")
    sys.exit(asyncio.run(principal(parser.parse_args())))
