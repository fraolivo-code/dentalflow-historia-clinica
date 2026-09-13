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

- `periodontograma_registro.recesion_mm`: modelado como medida en mm por
  sitio. La especificación dice "recesión (Cairo)", que podría referirse a
  la clasificación Cairo (RT1/RT2/RT3) en vez de una medida — confirmar con
  la Dra.
- `sitio_periodontal` (6 sitios): nomenclatura genérica
  vestibular/palatino-lingual, pendiente de validar contra la convención
  exacta que use la Dra.
- `consentimiento.archivo`: por ahora es solo texto (ruta/URL). Falta
  decidir dónde se aloja el archivo físico (Railway volume, S3, etc.) —
  no bloquea el esquema.
- `paciente` y `visita` son versiones mínimas acordadas a partir del
  proceso, no el cierre formal completo de la Etapa 1 — se ampliarán
  (antecedentes estructurados, etc.) sin romper este esquema base.
- Formas anatómicas reales (SVG) de cada diente: pendiente, fuera de
  alcance de esta etapa — por ahora la lógica de interacción usa raíces
  genéricas (1/2/3 según tipo de diente).
