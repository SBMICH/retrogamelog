"""Cinco intentos fallidos con un mismo correo lo bloquean 15 minutos."""

from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

from app.api.routes import auth as auth_routes
from app.main import app, create_app
from app.models import LoginAttempt

REGISTRO = "/api/v1/auth/register"
LOGIN = "/api/v1/auth/login"
EMAIL = "ana@example.com"
CLAVE = "retro-llave-42"
MALA = "no-es-la-clave-1"


@pytest.fixture
def client(db):
    client = TestClient(app)
    response = client.post(
        REGISTRO, json={"email": EMAIL, "username": "ana", "password": CLAVE}
    )
    assert response.status_code == 201
    return client


def entrar(client, password=CLAVE, email=EMAIL):
    return client.post(LOGIN, data={"username": email, "password": password})


def fallar(client, veces, email=EMAIL):
    return [entrar(client, MALA, email).status_code for _ in range(veces)]


def intento(db, email=EMAIL):
    db.rollback()
    db.expire_all()
    return db.get(LoginAttempt, email)


def retrasar(db, columna, minutos, email=EMAIL):
    """Simula que pasó el tiempo moviendo una marca hacia atrás."""
    db.execute(
        text(
            f"UPDATE login_attempts SET {columna} = now() - make_interval(mins => :m) "
            "WHERE email = :e"
        ),
        {"m": minutos, "e": email},
    )
    db.commit()


def test_los_cinco_primeros_fallos_responden_401_y_el_sexto_429(client):
    assert fallar(client, 5) == [401] * 5

    response = entrar(client, MALA)

    assert response.status_code == 429
    assert 890 <= int(response.headers["retry-after"]) <= 900
    assert "Demasiados intentos" in response.json()["detail"]


def test_bloqueado_tampoco_entra_la_contrasena_correcta(client):
    fallar(client, 5)

    assert entrar(client).status_code == 429


def test_el_quinto_intento_todavia_puede_acertar(client, db):
    fallar(client, 4)

    assert entrar(client).status_code == 200
    assert intento(db) is None


def test_un_inicio_correcto_reinicia_el_contador(client):
    fallar(client, 4)
    entrar(client)

    assert fallar(client, 5) == [401] * 5


def test_un_correo_sin_cuenta_se_bloquea_igual(client):
    con_cuenta = fallar(client, 7)
    sin_cuenta = fallar(client, 7, "nadie@example.com")

    assert sin_cuenta == con_cuenta == [401] * 5 + [429] * 2


def test_mayusculas_y_espacios_comparten_el_contador(client):
    for variante in (EMAIL, EMAIL.upper(), f"  {EMAIL} ", "Ana@Example.com", EMAIL):
        assert entrar(client, MALA, variante).status_code == 401

    assert entrar(client, CLAVE, "ANA@example.com").status_code == 429


def test_el_bloqueo_no_afecta_a_otros_correos(client):
    fallar(client, 6, "nadie@example.com")

    assert entrar(client).status_code == 200


def test_al_terminar_el_bloqueo_se_puede_entrar(client, db):
    fallar(client, 5)
    retrasar(db, "locked_until", 1)

    assert entrar(client).status_code == 200


def test_tras_el_bloqueo_vuelven_a_contarse_cinco(client, db):
    fallar(client, 5)
    retrasar(db, "locked_until", 1)

    assert fallar(client, 6) == [401] * 5 + [429]


def test_los_fallos_antiguos_no_se_acumulan(client, db):
    fallar(client, 4)
    retrasar(db, "last_attempt_at", 16)

    assert fallar(client, 4) == [401] * 4
    assert intento(db).failures == 4


def test_insistir_no_alarga_el_bloqueo(client, db):
    fallar(client, 5)
    antes = intento(db).locked_until

    fallar(client, 3)

    assert intento(db).locked_until == antes


def test_bloqueado_no_se_calcula_ningun_hash(client, monkeypatch):
    fallar(client, 5)
    verificaciones = []
    monkeypatch.setattr(auth_routes, "verify_password", lambda *args: verificaciones.append(args))

    entrar(client, MALA)

    assert verificaciones == []


def test_las_contrasenas_demasiado_largas_tambien_cuentan(client):
    for _ in range(5):
        assert entrar(client, "a1" * 100).status_code == 401

    assert entrar(client).status_code == 429


def test_el_bloqueo_sobrevive_a_un_reinicio(client):
    fallar(client, 5)

    assert entrar(TestClient(create_app())).status_code == 429


def test_un_correo_imposible_no_crea_filas(client, db):
    for valor in ("no es un correo", "ana\x00@example.com", "a" * 5000 + "@example.com"):
        assert entrar(client, MALA, valor).status_code == 401

    assert db.scalar(select(func.count()).select_from(LoginAttempt)) == 0


def test_intentos_simultaneos_no_superan_el_limite(client, monkeypatch):
    verificaciones = []
    original = auth_routes.verify_password

    def espia(password_hash, password):
        verificaciones.append(password)
        return original(password_hash, password)

    monkeypatch.setattr(auth_routes, "verify_password", espia)

    with ThreadPoolExecutor(max_workers=12) as pool:
        codigos = list(pool.map(lambda _: entrar(TestClient(app), MALA).status_code, range(24)))

    assert sorted(codigos) == [401] * 5 + [429] * 19
    assert len(verificaciones) == 5
