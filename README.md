# Fase 2 — Historia Clínica Digital

Módulo de historia clínica digital (odontograma general + periodontal) para
el consultorio de la Dra. Granados. Primer módulo de la Fase 2, construido
desde cero.

Especificación de referencia: `../Fase2- Historia-Clinica/Docs/especificacion-tecnica-odontograma-fase2.md`
(fuente de verdad del modelo de datos y la nomenclatura del odontograma).

## Stack

- Python + SQLAlchemy (async, `asyncpg`) + Alembic para migraciones versionadas.
- FastAPI para la API REST (async, integra bien con SQLAlchemy async y valida
  con Pydantic).
- Postgres en Railway — mismo proveedor que `fase1-whatsapp-bot`, sin fallback
  a SQLite: este módulo nace directo sobre Postgres.
- IDs en UUID en todas las tablas de este módulo (decisión deliberada,
  distinta al patrón `Integer` autoincremental de Fase 1 — pensando en un
  eventual producto multi-clínica).
- Sin autenticación todavía: cada request de escritura exige `creado_por`
  (UUID de un `usuario`) explícito en el body — no hay sesión/login que lo
  infiera.

## Estructura

```
backend/
  app/
    db.py            # engine async, sesion, Base declarativa
    deps.py          # dependencia get_session (FastAPI)
    enums.py         # catalogos fijos (tipo_hallazgo, superficie, etc.)
    main.py          # instancia FastAPI + incluye routers
    models/
      common.py      # mixins: UUIDPk, AuditMixin (seccion 0.1)
      usuario.py      # tabla minima para creado_por/actualizado_por
      paciente.py      # version minima acordada (se amplia en Etapa 1 formal)
      visita.py        # idem
      odontograma.py   # diente_anatomia, odontograma_hallazgo,
                       # odontograma_lesion_apical, puente_fijo, puente_fijo_diente
      periodontograma.py  # periodontograma_registro, periodontograma_diente_resumen
      consentimiento.py
    schemas/          # Pydantic: un archivo por dominio, espejo de models/
    services/
      odontograma_logic.py  # logica de interaccion (seccion 3): reglas de
                             # exclusividad (3.3), orden anatomico real para
                             # modo puente (3.2), calculo periapical/
                             # periimplantitis (1.3)
    routers/           # endpoints FastAPI, un archivo por recurso
  alembic/
    env.py           # corre sincrono (psycopg2) aunque la app use asyncpg
    versions/
      0001_initial_schema.py   # crea todo el esquema + siembra diente_anatomia
  alembic.ini
  requirements.txt
  .env.example
  tests/             # vacio por ahora
```

## Uso local

```bash
cd backend
python -m venv .venv && .venv\Scripts\activate   # Windows
pip install -r requirements.txt
cp .env.example .env   # y completar DATABASE_URL
alembic upgrade head
uvicorn app.main:app --reload   # docs interactivas en /docs
```

## Endpoints principales

- `usuario`, `paciente`, `visita`: CRUD basico (crear/listar/obtener).
- `GET /dientes`, `GET /dientes/{numero_diente}`: catalogo `diente_anatomia`.
- `GET /pacientes/{id}/odontograma`: hallazgos activos de todo el paciente.
- `POST /pacientes/{id}/dientes/{n}/hallazgos`: aplica un hallazgo respetando
  las reglas de exclusividad (3.3) — desactiva automaticamente los hallazgos
  incompatibles del mismo diente en vez de borrarlos.
- `POST /pacientes/{id}/dientes/{n}/lesion-apical`: valida la raiz contra
  `diente_anatomia` y calcula periapical/periimplantitis segun si el diente
  tiene "implante" activo (el cliente nunca manda `tipo`).
- `POST /pacientes/{id}/puentes`: crea `puente_fijo` + `puente_fijo_diente`,
  valida `condicion_individual` contra el subconjunto permitido, y devuelve
  los dientes en orden anatómico real (3.2), no numérico.
- `POST /visitas/{id}/periodontograma`: carga completa (registros por sitio +
  resumen por diente) de un levantamiento periodontal.
- `consentimiento`: crear/listar por paciente.

## Notas abiertas (no bloquean, pero pendientes de cerrar)

- ~~`recesion_mm` vs. Cairo~~ y ~~nomenclatura de sitios~~: cerrados con la
  Dra. el 24/09/2026 (migración 0010). Se guardan las dos: `recesion_mm` y
  `recesion_cairo` (RT1/RT2/RT3, opcional). `palatino_lingual` queda como
  valor interno; el frontend lo muestra como palatino/lingual según el arco.
- `consentimiento.archivo`: por ahora es solo texto (ruta/URL). Falta
  decidir dónde se aloja el archivo físico (Railway volume, S3, etc.) —
  no bloquea el esquema.
- `paciente` y `visita` son versiones mínimas acordadas a partir del
  proceso, no el cierre formal completo de la Etapa 1 — se ampliarán
  (antecedentes estructurados, etc.) sin romper este esquema base.
- Formas anatómicas reales (SVG) de cada diente: pendiente, fuera de
  alcance de esta etapa — por ahora la lógica de interacción usa raíces
  genéricas (1/2/3 según tipo de diente).

## Borrar un paciente de prueba (procedimiento aparte)

La aplicación **no** borra pacientes ni registros clínicos (a propósito). Para quitar de
producción un paciente de **prueba** con todo lo que depende de él (visitas, bitácora,
odontograma, exámenes, tratamientos…) existe `backend/scripts/borrar_paciente.py`. Lo ejecuta
Francisco; la Dra. no.

1. Correr el respaldo («Run now» en `dentalflow-backup-cron`) y esperar el correo «Backup OK».
2. Ensayo (no borra nada; lista las filas que se borrarían):
   `railway ssh --service dentalflow-historia-clinica-api -- "python scripts/borrar_paciente.py --historia 000434"`
3. Si el ensayo es lo esperado, borrado real:
   `railway ssh --service dentalflow-historia-clinica-api -- "python scripts/borrar_paciente.py --historia 000434 --ejecutar --confirmo 'BORRAR 000434'"`

El script se niega si el nombre del paciente no contiene «prueba» (salvo `--forzar-no-prueba`),
recorre las claves foráneas del modelo (una tabla nueva entra sola) y borra todo en una sola
transacción. No toca usuarios, profesionales ni catálogos.

## Pasar historias aprobadas a «en carga» (procedimiento aparte)

La aplicación no permite devolver una historia aprobada a «en carga». Si hace falta (por ejemplo,
las historias que ya existían al crear el estado quedaron «aprobada» y están incompletas), lo hace
Francisco con `backend/scripts/reabrir_carga.py`. No borra nada.

Paso a paso (en la terminal, dentro de la carpeta `Fase2-Historia-Clinica-App/repo`):

1. Correr el respaldo («Run now» en `dentalflow-backup-cron`) y esperar el correo «Backup OK».
2. Comprobar que Railway está conectado: `railway status` debe mostrar el proyecto. Si pide
   iniciar sesión: `railway login`.
3. Ensayo (no cambia nada; muestra qué historias cambiarían):
   `railway ssh --service dentalflow-historia-clinica-api -- "python scripts/reabrir_carga.py --historia 000317 --historia 000433"`
4. Si las líneas mostradas son las historias correctas, aplicar (se agrega `--ejecutar`):
   `railway ssh --service dentalflow-historia-clinica-api -- "python scripts/reabrir_carga.py --historia 000317 --historia 000433 --ejecutar"`
5. Comprobar en la aplicación: la ficha muestra «Historia en carga» y la búsqueda «En carga».

Cambiar los números de historia según corresponda; `--historia` se repite una vez por historia.

## Enlazar a la visita lo cargado en un día (procedimiento aparte)

Desde el 15/10/2026 «Tratamiento realizado» queda dentro de la visita que tenga la misma fecha. Lo que se
cargó antes quedó suelto (sin visita) y no aparece en «Lo realizado ese día». Lo arregla Francisco con
`backend/scripts/enlazar_visita.py`. No borra nada ni cambia fechas: solo enlaza a la visita de ese día las
entradas de bitácora y los hallazgos de esa fecha que no tienen visita.

Paso a paso (en la terminal, dentro de la carpeta `Fase2-Historia-Clinica-App/repo`):

1. Debe existir **una sola visita** con esa fecha en la ficha (si no, créela con «Iniciar visita»).
2. Correr el respaldo («Run now» en `dentalflow-backup-cron`) y esperar el correo «Backup OK».
3. Ensayo (no cambia nada; lista lo que se enlazaría). Cambiar la historia y la fecha (AAAA-MM-DD):
   `railway ssh --service dentalflow-historia-clinica-api -- "python scripts/enlazar_visita.py --historia 000317 --fecha 2019-04-23"`
4. Si lo listado es lo esperado, aplicar (se agrega `--ejecutar`):
   `railway ssh --service dentalflow-historia-clinica-api -- "python scripts/enlazar_visita.py --historia 000317 --fecha 2019-04-23 --ejecutar"`
5. Recargar la ficha: la visita muestra «Lo realizado ese día (N)».

## Eliminar una entrada de bitácora (procedimiento aparte)

La ficha ya no tiene la sección «Bitácora» general. Si una nota quedó pegada a un diente y era de toda la
visita (por ejemplo, «Adaptación a la consulta»), la nota de la visita se escribe en la visita («Nota de la
visita») y la entrada vieja la quita Francisco con `backend/scripts/eliminar_entrada_bitacora.py`. Solo borra
esa entrada y sus dientes: **no toca los hallazgos del odontograma**. Solo en historias «en carga».

Paso a paso (en la terminal, dentro de la carpeta `Fase2-Historia-Clinica-App/repo`):

1. Escribir antes la nota en la visita («Editar» en la visita → «Nota de la visita»).
2. Correr el respaldo («Run now» en `dentalflow-backup-cron`) y esperar el correo «Backup OK».
3. Ensayo (no borra nada; muestra la entrada que se eliminaría). Cambiar historia, fecha (AAAA-MM-DD) y diente:
   `railway ssh --service dentalflow-historia-clinica-api -- "python scripts/eliminar_entrada_bitacora.py --historia 000334 --fecha 2019-04-17 --diente 55"`
4. Si es la entrada correcta, eliminar (se agrega `--ejecutar`):
   `railway ssh --service dentalflow-historia-clinica-api -- "python scripts/eliminar_entrada_bitacora.py --historia 000334 --fecha 2019-04-17 --diente 55 --ejecutar"`
5. Recargar la ficha: la nota ya no aparece como «Nota (diente 55)» y sí como «Nota de la visita».
