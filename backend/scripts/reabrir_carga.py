"""Pasa historias APROBADAS de vuelta a «en carga» (la aplicacion no lo permite).

Se usa una vez: las historias que existian al crear el estado (migracion 0033) quedaron
«aprobada» y, si aun estan incompletas, hay que reabrirlas para poder cargarlas y corregirlas.

Antes: respaldo («Run now») y correo "Backup OK".

  Ensayo (no cambia nada):
    python scripts/reabrir_carga.py --historia 000311 --historia 000433

  Real:
    python scripts/reabrir_carga.py --historia 000311 --historia 000433 --ejecutar
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import async_session  # noqa: E402
from app.enums import EstadoHistoria  # noqa: E402
from app.services import borrado_paciente  # noqa: E402


async def principal(args: argparse.Namespace) -> int:
    async with async_session() as session:
        pacientes = []
        for h in args.historia:
            p = await borrado_paciente.buscar_por_historia(session, h)
            if p is None:
                print(f"No existe la historia {h}. No se cambio nada.")
                return 1
            pacientes.append(p)
        for p in pacientes:
            print(f"{p.numero_historia} — {p.nombre_completo}: {p.estado_historia.value} -> en_carga")
        if not args.ejecutar:
            print("\nENSAYO: no se cambio nada. Agregue --ejecutar para aplicar.")
            return 0
        for p in pacientes:
            if p.estado_historia == EstadoHistoria.en_carga:
                continue
            p.estado_historia = EstadoHistoria.en_carga
            p.aprobada_en = None
            p.aprobada_por = None
        await session.commit()
        print("\nListo.")
        return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--historia", action="append", required=True, help="Numero de historia (repetible)")
    parser.add_argument("--ejecutar", action="store_true")
    sys.exit(asyncio.run(principal(parser.parse_args())))
