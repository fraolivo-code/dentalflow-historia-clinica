# Pantallas clinicas, ANEXO A (04/10/2026): bitacora con varios dientes y atomica,
# permisos de consentimientos y vinculo usuario-profesional.
# Especificacion: especificacion-tecnica-pantallas-clinicas.md.

import uuid
from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy import select

from app import security
from app.enums import (
    EstadoGeneralPuente,
    RolDientePuente,
    RolUsuario,
    TipoHallazgo,
)
from app.models import (
    AuditoriaUsuario,
    BitacoraDiente,
    BitacoraTratamiento,
    Consentimiento,
    OdontogramaHallazgo,
    ProfesionalTratante,
    PuenteFijo,
    PuenteFijoDiente,
    Usuario,
)


@pytest_asyncio.fixture
async def usuarios(session_factory):
    ids = {}
    async with session_factory() as s:
        for nombre, rol in (
            ("doctora", RolUsuario.dra),
            ("asistente", RolUsuario.asistente),
            ("otra", RolUsuario.asistente),
        ):
            u = Usuario(nombre=nombre, rol=rol, password_hash="x", email=f"{nombre}@e.com")
            s.add(u)
            await s.flush()
            ids[nombre] = u.id
        await s.commit()
    return ids


@pytest.fixture
def h_dra(usuarios):
    return {"Authorization": f"Bearer {security.crear_access_token(usuarios['doctora'], 'dra')}"}


@pytest.fixture
def h_asistente(usuarios):
    token = security.crear_access_token(usuarios["asistente"], "asistente")
    return {"Authorization": f"Bearer {token}"}


async def _paciente(client, h, nombre="Paciente Prueba"):
    r = await client.post(
        "/pacientes",
        headers=h,
        json={"movil": "04141234567", "nombre_completo": nombre, "fecha_registro": "2026-10-05"},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _tratamiento(client, h, paciente_id):
    prof = await client.post("/profesionales-tratantes", headers=h, json={"nombre": "Dra. Prueba"})
    r = await client.post(
        f"/pacientes/{paciente_id}/tratamientos",
        headers=h,
        json={
            "tipo": "endodoncia",
            "fecha_inicio": "2026-09-01",
            "profesional_tratante_id": prof.json()["id"],
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _entrada(**extra):
    return {"fecha": "2026-10-01", "descripcion": "Sesión de prueba", **extra}


async def _bitacora(client, h, pid, **extra):
    return await client.post(f"/pacientes/{pid}/bitacora", headers=h, json=_entrada(**extra))


async def _contar(session_factory, modelo):
    async with session_factory() as s:
        return len((await s.execute(select(modelo))).scalars().all())


async def _puente_activo(session_factory, usuarios, paciente_id, dientes):
    async with session_factory() as s:
        puente = PuenteFijo(
            paciente_id=uuid.UUID(paciente_id),
            estado_general=EstadoGeneralPuente.ok,
            fecha=date(2026, 9, 1),
            creado_por=usuarios["doctora"],
        )
        s.add(puente)
        await s.flush()
        for n in dientes:
            s.add(
                PuenteFijoDiente(
                    puente_id=puente.id,
                    numero_diente=n,
                    rol=RolDientePuente.pilar,
                    condicion_individual=TipoHallazgo.sano,
                    creado_por=usuarios["doctora"],
                )
            )
        await s.commit()


# ============================================================ A.1 bitacora


async def test_varios_dientes_con_hallazgo_crea_uno_por_diente(client, h_dra, session_factory):
    pid = await _paciente(client, h_dra)
    r = await _bitacora(client, h_dra, pid, dientes=[21, 11, 12], tipo_hallazgo="conducto_ok")
    assert r.status_code == 201, r.text
    cuerpo = r.json()
    assert cuerpo["dientes"] == [12, 11, 21]  # orden anatomico
    assert cuerpo["numero_diente"] == 21  # compatibilidad: el primero recibido
    odontograma = (await client.get(f"/pacientes/{pid}/odontograma", headers=h_dra)).json()
    assert sorted(h["numero_diente"] for h in odontograma) == [11, 12, 21]
    assert await _contar(session_factory, BitacoraDiente) == 3
    assert await _contar(session_factory, BitacoraTratamiento) == 1


async def test_varios_dientes_sin_hallazgo_no_toca_el_odontograma(client, h_dra):
    pid = await _paciente(client, h_dra)
    r = await _bitacora(client, h_dra, pid, dientes=[11, 21])
    assert r.status_code == 201
    assert r.json()["dientes"] == [11, 21]
    assert (await client.get(f"/pacientes/{pid}/odontograma", headers=h_dra)).json() == []


async def test_entrada_sin_dientes(client, h_dra):
    pid = await _paciente(client, h_dra)
    r = await _bitacora(client, h_dra, pid)
    assert (r.status_code, r.json()["dientes"], r.json()["numero_diente"]) == (201, [], None)


async def test_fallo_en_un_diente_no_guarda_nada(client, h_dra, usuarios, session_factory):
    pid = await _paciente(client, h_dra)
    await _puente_activo(session_factory, usuarios, pid, [21, 22])
    # 11 y 12 se aplicarian bien; 21 forma parte de un puente activo: 409.
    r = await _bitacora(client, h_dra, pid, dientes=[11, 12, 21], tipo_hallazgo="conducto_ok")
    assert r.status_code == 409
    detalle = r.json()["detail"]
    assert "diente 21" in detalle["mensaje"] and "No se guardó la entrada" in detalle["mensaje"]
    assert "puente_existente_id" in detalle
    assert await _contar(session_factory, BitacoraTratamiento) == 0
    assert await _contar(session_factory, BitacoraDiente) == 0
    assert await _contar(session_factory, OdontogramaHallazgo) == 0
    assert (await client.get(f"/pacientes/{pid}/bitacora", headers=h_dra)).json() == []


async def test_hallazgo_duplicado_activo_se_omite_sin_error(client, h_dra, session_factory):
    pid = await _paciente(client, h_dra)
    assert (await _bitacora(client, h_dra, pid, dientes=[11], tipo_hallazgo="conducto_ok")).status_code == 201
    r = await _bitacora(client, h_dra, pid, dientes=[11, 12], tipo_hallazgo="conducto_ok")
    assert r.status_code == 201
    assert await _contar(session_factory, BitacoraTratamiento) == 2
    assert await _contar(session_factory, OdontogramaHallazgo) == 2  # 11 (ya) + 12 (nuevo)


async def test_tratamiento_de_otro_paciente_es_422_y_no_guarda(client, h_dra, session_factory):
    a = await _paciente(client, h_dra, "Paciente A")
    b = await _paciente(client, h_dra, "Paciente B")
    trat_a = await _tratamiento(client, h_dra, a)
    r = await _bitacora(client, h_dra, b, tratamiento_id=trat_a, dientes=[11])
    assert r.status_code == 422
    assert await _contar(session_factory, BitacoraTratamiento) == 0
    ok = await _bitacora(client, h_dra, a, tratamiento_id=trat_a, dientes=[11])
    assert ok.status_code == 201 and ok.json()["tratamiento_id"] == trat_a


async def test_tratamiento_inexistente_sigue_siendo_404(client, h_dra):
    pid = await _paciente(client, h_dra)
    r = await _bitacora(client, h_dra, pid, tratamiento_id=str(uuid.uuid4()))
    assert r.status_code == 404


async def test_numero_diente_suelto_sigue_funcionando(client, h_dra):
    pid = await _paciente(client, h_dra)
    r = await _bitacora(client, h_dra, pid, numero_diente=16, tipo_hallazgo="conducto_ok")
    assert r.status_code == 201
    assert (r.json()["numero_diente"], r.json()["dientes"]) == (16, [16])
    odontograma = (await client.get(f"/pacientes/{pid}/odontograma", headers=h_dra)).json()
    assert [h["numero_diente"] for h in odontograma] == [16]


async def test_numero_diente_suelto_se_suma_a_la_lista_sin_repetir(client, h_dra):
    pid = await _paciente(client, h_dra)
    r = await _bitacora(client, h_dra, pid, dientes=[11, 12], numero_diente=12)
    assert r.json()["dientes"] == [12, 11]
    r = await _bitacora(client, h_dra, pid, dientes=[11], numero_diente=21)
    assert r.json()["dientes"] == [11, 21]
    r = await _bitacora(client, h_dra, pid, dientes=[11, 11])
    assert r.json()["dientes"] == [11]


async def test_dientes_invalidos_son_422(client, h_dra, session_factory):
    pid = await _paciente(client, h_dra)
    assert (await _bitacora(client, h_dra, pid, dientes=[11, 99])).status_code == 422
    assert (await _bitacora(client, h_dra, pid, numero_diente=99)).status_code == 422
    assert await _contar(session_factory, BitacoraTratamiento) == 0


async def test_superficie_invalida_para_el_hallazgo_es_422(client, h_dra):
    pid = await _paciente(client, h_dra)
    r = await _bitacora(client, h_dra, pid, dientes=[11], tipo_hallazgo="caries")  # sin superficie
    assert r.status_code == 422


async def test_listar_y_ver_devuelven_los_dientes(client, h_dra):
    pid = await _paciente(client, h_dra)
    creada = (await _bitacora(client, h_dra, pid, dientes=[21, 11])).json()
    lista = (await client.get(f"/pacientes/{pid}/bitacora", headers=h_dra)).json()
    assert [e["dientes"] for e in lista] == [[11, 21]]
    uno = (await client.get(f"/bitacora/{creada['id']}", headers=h_dra)).json()
    assert uno["dientes"] == [11, 21]


async def test_entrada_vieja_sin_filas_en_bitacora_diente_cae_a_su_columna(
    client, h_dra, usuarios, session_factory
):
    pid = await _paciente(client, h_dra)
    async with session_factory() as s:
        s.add(
            BitacoraTratamiento(
                paciente_id=uuid.UUID(pid),
                fecha=date(2020, 1, 1),
                responsable=usuarios["doctora"],
                descripcion="Entrada anterior a la 0022",
                numero_diente=36,
                creado_por=usuarios["doctora"],
            )
        )
        await s.commit()
    lista = (await client.get(f"/pacientes/{pid}/bitacora", headers=h_dra)).json()
    assert lista[0]["dientes"] == [36]


async def test_bitacora_solo_para_acceso_total(client, h_dra, h_asistente):
    pid = await _paciente(client, h_dra)
    assert (await _bitacora(client, h_asistente, pid, dientes=[11])).status_code == 403
    assert (await client.get(f"/pacientes/{pid}/bitacora", headers=h_asistente)).status_code == 403


# ===================================================== A.2 consentimientos


def _consent(tipo, **extra):
    return {"tipo": tipo, "fecha": "2026-10-01", "archivo": "En papel", **extra}


async def test_consentimiento_de_tratamiento_solo_acceso_total(client, h_dra, h_asistente):
    pid = await _paciente(client, h_dra)
    trat = await _tratamiento(client, h_dra, pid)
    r = await client.post(
        f"/pacientes/{pid}/consentimientos", headers=h_asistente, json=_consent("tratamiento", tratamiento_id=trat)
    )
    assert r.status_code == 403
    r = await client.post(
        f"/pacientes/{pid}/consentimientos", headers=h_dra, json=_consent("tratamiento", tratamiento_id=trat)
    )
    assert r.status_code == 201 and r.json()["tratamiento_id"] == trat


async def test_consentimiento_de_tratamiento_exige_tratamiento_del_mismo_paciente(
    client, h_dra, session_factory
):
    a = await _paciente(client, h_dra, "Paciente A")
    b = await _paciente(client, h_dra, "Paciente B")
    trat_a = await _tratamiento(client, h_dra, a)
    sin = await client.post(f"/pacientes/{b}/consentimientos", headers=h_dra, json=_consent("tratamiento"))
    assert sin.status_code == 422
    otro = await client.post(
        f"/pacientes/{b}/consentimientos", headers=h_dra, json=_consent("tratamiento", tratamiento_id=trat_a)
    )
    assert otro.status_code == 404
    inexistente = await client.post(
        f"/pacientes/{a}/consentimientos",
        headers=h_dra,
        json=_consent("tratamiento", tratamiento_id=str(uuid.uuid4())),
    )
    assert inexistente.status_code == 404
    assert await _contar(session_factory, Consentimiento) == 0


async def test_consentimiento_de_almacenamiento_digital_lo_registran_ambos_sin_tratamiento(
    client, h_dra, h_asistente
):
    pid = await _paciente(client, h_dra)
    trat = await _tratamiento(client, h_dra, pid)
    for h in (h_asistente, h_dra):
        r = await client.post(
            f"/pacientes/{pid}/consentimientos", headers=h, json=_consent("almacenamiento_digital")
        )
        assert r.status_code == 201 and r.json()["tratamiento_id"] is None
        con = await client.post(
            f"/pacientes/{pid}/consentimientos",
            headers=h,
            json=_consent("almacenamiento_digital", tratamiento_id=trat),
        )
        assert con.status_code == 422


async def test_listado_de_consentimientos_segun_el_rol(client, h_dra, h_asistente):
    pid = await _paciente(client, h_dra)
    trat = await _tratamiento(client, h_dra, pid)
    await client.post(f"/pacientes/{pid}/consentimientos", headers=h_dra, json=_consent("almacenamiento_digital"))
    await client.post(
        f"/pacientes/{pid}/consentimientos", headers=h_dra, json=_consent("tratamiento", tratamiento_id=trat)
    )
    total = (await client.get(f"/pacientes/{pid}/consentimientos", headers=h_dra)).json()
    assert sorted(c["tipo"] for c in total) == ["almacenamiento_digital", "tratamiento"]
    de_asistente = (await client.get(f"/pacientes/{pid}/consentimientos", headers=h_asistente)).json()
    assert [c["tipo"] for c in de_asistente] == ["almacenamiento_digital"]
    assert (await client.get(f"/pacientes/{pid}/consentimientos")).status_code == 401


async def test_consentimiento_de_paciente_inexistente_es_404(client, h_dra):
    r = await client.post(
        f"/pacientes/{uuid.uuid4()}/consentimientos", headers=h_dra, json=_consent("almacenamiento_digital")
    )
    assert r.status_code == 404


# ============================================ A.3 usuario <-> profesional


async def _profesional(client, h, nombre):
    r = await client.post("/profesionales-tratantes", headers=h, json={"nombre": nombre})
    assert r.status_code == 201
    return r.json()["id"]


async def _vincular(client, h, usuario_id, profesional_id):
    return await client.patch(
        f"/usuarios/{usuario_id}", headers=h, json={"profesional_tratante_id": profesional_id}
    )


async def _acciones(session_factory):
    async with session_factory() as s:
        return (await s.execute(select(AuditoriaUsuario.accion))).scalars().all()


async def test_vincular_y_ver_el_profesional(client, h_dra, usuarios, session_factory):
    prof = await _profesional(client, h_dra, "Leonor Granados")
    r = await _vincular(client, h_dra, usuarios["doctora"], prof)
    assert r.status_code == 200
    assert r.json()["profesional"] == {"id": prof, "nombre": "Leonor Granados"}
    uno = (await client.get(f"/usuarios/{usuarios['doctora']}", headers=h_dra)).json()
    assert uno["profesional"]["nombre"] == "Leonor Granados"
    lista = {u["nombre"]: u["profesional"] for u in (await client.get("/usuarios", headers=h_dra)).json()}
    assert lista["doctora"]["id"] == prof and lista["asistente"] is None
    assert "profesional_vinculado" in await _acciones(session_factory)
    async with session_factory() as s:
        fila = await s.get(ProfesionalTratante, uuid.UUID(prof))
        assert fila.usuario_id == usuarios["doctora"]


async def test_desvincular_con_null(client, h_dra, usuarios, session_factory):
    prof = await _profesional(client, h_dra, "Leonor Granados")
    await _vincular(client, h_dra, usuarios["doctora"], prof)
    r = await _vincular(client, h_dra, usuarios["doctora"], None)
    assert r.status_code == 200 and r.json()["profesional"] is None
    assert "profesional_desvinculado" in await _acciones(session_factory)
    async with session_factory() as s:
        assert (await s.get(ProfesionalTratante, uuid.UUID(prof))).usuario_id is None
    # sin vinculo previo, null no hace nada ni audita otra vez
    antes = (await _acciones(session_factory)).count("profesional_desvinculado")
    assert (await _vincular(client, h_dra, usuarios["doctora"], None)).status_code == 200
    assert (await _acciones(session_factory)).count("profesional_desvinculado") == antes


async def test_un_profesional_no_puede_estar_en_dos_usuarios(client, h_dra, usuarios):
    prof = await _profesional(client, h_dra, "Leonor Granados")
    assert (await _vincular(client, h_dra, usuarios["doctora"], prof)).status_code == 200
    r = await _vincular(client, h_dra, usuarios["asistente"], prof)
    assert r.status_code == 409
    assert r.json()["detail"] == "Ese profesional ya está vinculado a otro usuario."
    quedo = (await client.get(f"/usuarios/{usuarios['doctora']}", headers=h_dra)).json()
    assert quedo["profesional"]["id"] == prof


async def test_vincular_otro_profesional_reemplaza_al_anterior(client, h_dra, usuarios, session_factory):
    uno = await _profesional(client, h_dra, "Uno")
    dos = await _profesional(client, h_dra, "Dos")
    await _vincular(client, h_dra, usuarios["doctora"], uno)
    r = await _vincular(client, h_dra, usuarios["doctora"], dos)
    assert r.status_code == 200 and r.json()["profesional"]["id"] == dos
    async with session_factory() as s:
        assert (await s.get(ProfesionalTratante, uuid.UUID(uno))).usuario_id is None
    acciones = await _acciones(session_factory)
    assert acciones.count("profesional_vinculado") == 2 and acciones.count("profesional_desvinculado") == 1


async def test_vincular_el_mismo_profesional_no_cambia_nada(client, h_dra, usuarios, session_factory):
    prof = await _profesional(client, h_dra, "Leonor Granados")
    await _vincular(client, h_dra, usuarios["doctora"], prof)
    assert (await _vincular(client, h_dra, usuarios["doctora"], prof)).status_code == 200
    assert (await _acciones(session_factory)).count("profesional_vinculado") == 1


async def test_vincular_profesional_inexistente_es_404(client, h_dra, usuarios):
    assert (await _vincular(client, h_dra, usuarios["doctora"], str(uuid.uuid4()))).status_code == 404


async def test_vincular_solo_acceso_total(client, h_asistente, h_dra, usuarios):
    prof = await _profesional(client, h_dra, "Leonor Granados")
    assert (await _vincular(client, h_asistente, usuarios["asistente"], prof)).status_code == 403


async def test_patch_sin_profesional_no_toca_el_vinculo(client, h_dra, usuarios):
    prof = await _profesional(client, h_dra, "Leonor Granados")
    await _vincular(client, h_dra, usuarios["asistente"], prof)
    r = await client.patch(f"/usuarios/{usuarios['asistente']}", headers=h_dra, json={"email": "nuevo@e.com"})
    assert r.status_code == 200 and r.json()["profesional"]["id"] == prof


async def test_documento_emitido_exige_el_vinculo(client, h_dra, usuarios, session_factory):
    # Sin vinculo, emitir un documento da 409; con el vinculo, funciona.
    pid = await _paciente(client, h_dra)
    cuerpo = {"contenido_final": "Indicaciones de prueba"}
    sin = await client.post(f"/pacientes/{pid}/indicaciones-tratamiento", headers=h_dra, json=cuerpo)
    assert sin.status_code == 409
    prof = await _profesional(client, h_dra, "Leonor Granados")
    await _vincular(client, h_dra, usuarios["doctora"], prof)
    # el router de indicaciones usa tablas que estos tests no crean: basta ver que ya no es 409 por vinculo
    from app.routers.constancias_asistencia import profesional_del_usuario

    async with session_factory() as s:
        u = await s.get(Usuario, usuarios["doctora"])
        assert (await profesional_del_usuario(u, s)).id == uuid.UUID(prof)


@pytest.mark.parametrize("ruta", ["/auth/me"])
async def test_me_sigue_respondiendo(client, h_dra, ruta):
    r = await client.get(ruta, headers=h_dra)
    assert r.status_code == 200 and r.json()["profesional"] is None
