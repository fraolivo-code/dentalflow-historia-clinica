"""Elimina UNA entrada de bitacora de un paciente (la ficha ya no tiene esa seccion).

Sirve para quitar una nota que quedo pegada a un diente y era de toda la visita (la nota de la
visita se escribe ahora en la visita). Solo borra la entrada de bitacora y sus dientes: NO toca los
hallazgos del odontograma. Solo funciona en historias «en carga».

ANTES de ejecutarlo de verdad:
  1. Corra el respaldo («Run now» en dentalflow-backup-cron) y espere el correo "Backup OK".
  2. Corra el ENSAYO (no borra nada) y lea cual entrada se borraria.

Uso (desde la carpeta backend, o dentro del contenedor de la API en Railway):

  Ensayo, no borra:
    python scripts/eliminar_entrada_bitacora.py --historia 000334 --fecha 2019-04-17 --diente 55

  Real:
    python scripts/eliminar_entrada_bitacora.py --historia 000334 --fecha 2019-04-17 --diente 55 --ejecutar

Si hay mas de una entrada que coincide, no borra ninguna: agregue --texto "parte del texto".
"""

import argparse
import asyncio
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.db import async_session  # noqa: E402
from app.models.bitacora_tratamiento import BitacoraDiente, BitacoraTratamiento  # noqa: E402
from app.services import borrado_paciente, eliminacion_carga  # noqa: E402


async def principal(args: argparse.Namespace) -> int:
    fecha = date.fromisoformat(args.fecha)
    async with async_session() as session:
        paciente = await borrado_paciente.buscar_por_historia(session, args.historia)
        if paciente is None:
            print(f"No existe la historia {args.historia}. No se borro nada.")
            return 1
        print(f"Paciente: historia {paciente.numero_historia} — {paciente.nombre_completo} ({paciente.estado_historia.value})")
        entradas = (
            await session.execute(
                select(BitacoraTratamiento).where(
                    BitacoraTratamiento.paciente_id == paciente.id, BitacoraTratamiento.fecha == fecha
                )
            )
        ).scalars().all()
        coinciden = []
        for e in entradas:
            dientes = set((await session.execute(select(BitacoraDiente.numero_diente).where(BitacoraDiente.bitacora_id == e.id))).scalars())
            if e.numero_diente is not None:
                dientes.add(e.numero_diente)
            if args.diente is not None and args.diente not in dientes:
                continue
            if args.texto and args.texto.lower() not in e.descripcion.lower():
                continue
            coinciden.append((e, sorted(dientes)))
        for e, dientes in coinciden:
            print(f"  - {e.id} · dientes {dientes} · {e.descripcion[:120]}")
        if len(coinciden) != 1:
            print(f"\nSe esperaba UNA entrada y hay {len(coinciden)}. No se borro nada (afine con --diente / --texto).")
            return 1
        if not args.ejecutar:
            print("\nENSAYO: no se borro nada. Agregue --ejecutar para eliminar esa entrada.")
            return 0
        await eliminacion_carga.exigir_en_carga(session, paciente.id)
        await eliminacion_carga.eliminar_registro(session, BitacoraTratamiento, coinciden[0][0].id)
        print("\nListo: entrada eliminada (los hallazgos del odontograma no se tocaron).")
        return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--historia", required=True, help="Numero de historia (ej. 000334 o 334)")
    parser.add_argument("--fecha", required=True, help="Fecha AAAA-MM-DD de la entrada")
    parser.add_argument("--diente", type=int, help="Numero de diente de la entrada")
    parser.add_argument("--texto", help="Parte del texto de la entrada")
    parser.add_argument("--ejecutar", action="store_true", help="Elimina de verdad (sin esto es solo un ensayo)")
    sys.exit(asyncio.run(principal(parser.parse_args())))
