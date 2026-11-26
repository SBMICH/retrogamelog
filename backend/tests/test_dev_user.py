"""El usuario de desarrollo solo puede crearse en un equipo de desarrollo."""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import dev_user
from app.dev_user import (
    DEV_EMAIL,
    DEV_USERNAME,
    LOOPBACK_ADDRESSES,
    connected_address,
    create_dev_user,
    main,
    refusal_reason,
)
from app.main import app
from app.models import User

ENTORNO_LOCAL = {
    "APP_ENV": "development",
    "DATABASE_URL": "postgresql+psycopg://u:p@localhost:5432/retrogamelog",
    "DEV_USER_PASSWORD": "123",
}


def contar(db):
    db.rollback()
    return db.scalar(select(func.count()).select_from(User))


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "[::1]"])
def test_un_entorno_local_de_desarrollo_se_acepta(host):
    entorno = {**ENTORNO_LOCAL, "DATABASE_URL": f"postgresql+psycopg://u:p@{host}:5432/x"}

    assert refusal_reason(entorno) is None


@pytest.mark.parametrize(
    "cambios",
    [
        pytest.param({"APP_ENV": None}, id="sin-app-env"),
        pytest.param({"APP_ENV": "production"}, id="produccion"),
        pytest.param({"RENDER": "true"}, id="servidor-render"),
        pytest.param(
            {"DATABASE_URL": "postgresql+psycopg://u:p@db.example.com:5432/x"}, id="base-remota"
        ),
        pytest.param(
            {"DATABASE_URL": "postgresql+psycopg://u:p@localhost/x?host=db.example.com"},
            id="host-oculto-en-la-url",
        ),
        pytest.param(
            {"DATABASE_URL": "postgresql+psycopg://u:p@localhost/x?hostaddr=10.0.0.9"},
            id="hostaddr-en-la-url",
        ),
        pytest.param(
            {
                "DATABASE_URL": "postgresql+psycopg://u:p@localhost/x"
                "?conninfo=hostaddr%3D10.0.0.9"
            },
            id="conninfo-en-la-url",
        ),
        pytest.param(
            {"DATABASE_URL": "postgresql+psycopg://u:p@localhost/x?service=produccion"},
            id="service-en-la-url",
        ),
        pytest.param(
            {"DATABASE_URL": "postgresql+psycopg://u:p@localhost/x?otro=1"},
            id="parametro-desconocido",
        ),
        pytest.param(
            {"DATABASE_URL": "postgresql+psycopg://u:p@localhost,db.example.com/x"},
            id="varios-servidores",
        ),
        pytest.param({"PGHOSTADDR": "10.0.0.9"}, id="variable-que-redirige"),
        pytest.param({"DATABASE_URL": None}, id="sin-base"),
        pytest.param({"DATABASE_URL": "no es una url secreta"}, id="url-invalida"),
        pytest.param({"DEV_USER_PASSWORD": None}, id="sin-contrasena"),
    ],
)
def test_fuera_de_desarrollo_se_rechaza(cambios):
    entorno = {k: v for k, v in {**ENTORNO_LOCAL, **cambios}.items() if v is not None}

    motivo = refusal_reason(entorno)

    assert motivo is not None
    assert "secreta" not in motivo


def test_el_comando_rechazado_no_crea_nada(db, monkeypatch, capsys):
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setenv("DEV_USER_PASSWORD", "123")

    assert main() == 2
    assert "APP_ENV=development" in capsys.readouterr().err
    assert contar(db) == 0


def test_connected_address_lee_la_direccion_de_la_conexion(db):
    """Sin esto, sustituirla por un valor fijo quitaría la segunda barrera sin que nada fallara."""

    class ConexionSimulada:
        def connection(self):
            info = SimpleNamespace(hostaddr="10.1.2.3")
            return SimpleNamespace(connection=SimpleNamespace(driver_connection=SimpleNamespace(info=info)))

    real = db.connection().connection.driver_connection.info.hostaddr

    assert connected_address(db) == real
    assert connected_address(ConexionSimulada()) == "10.1.2.3"


def test_los_parametros_inofensivos_se_aceptan():
    url = "postgresql+psycopg://u:p@localhost/x?sslmode=disable&connect_timeout=3"

    assert refusal_reason({**ENTORNO_LOCAL, "DATABASE_URL": url}) is None


@pytest.fixture
def entorno_de_desarrollo(monkeypatch):
    """El entorno real de los tests, con lo que pide el comando (la base de pruebas es local)."""
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("DEV_USER_PASSWORD", "123")
    for name in ("RENDER", "PGHOSTADDR", "PGSERVICE"):
        monkeypatch.delenv(name, raising=False)


def test_el_comando_crea_el_usuario_en_la_base_local(db, entorno_de_desarrollo):
    assert connected_address(db) in LOOPBACK_ADDRESSES

    assert main() == 0
    assert contar(db) == 1


def test_si_la_conexion_real_no_es_local_no_se_escribe(
    db, entorno_de_desarrollo, monkeypatch, capsys
):
    """Aunque la URL parezca local, manda la dirección a la que se conectó el cliente."""
    monkeypatch.setattr(dev_user, "connected_address", lambda db: "10.0.0.9")

    assert main() == 2
    assert "localhost" in capsys.readouterr().err
    assert contar(db) == 0


def test_el_usuario_creado_puede_iniciar_sesion_con_123(db):
    create_dev_user(db, "123")

    response = TestClient(app).post(
        "/api/v1/auth/login", data={"username": DEV_EMAIL, "password": "123"}
    )

    assert response.status_code == 200
    assert db.scalar(select(User.password_hash)).startswith("$argon2id$")


def test_repetirlo_no_duplica_ni_cambia_la_contrasena(db):
    create_dev_user(db, "123")
    antes = db.scalar(select(User.password_hash))

    mensaje = create_dev_user(db, "otra-clave-9")

    assert "ya existe" in mensaje
    assert contar(db) == 1
    assert db.scalar(select(User.password_hash)) == antes


@pytest.mark.parametrize(
    "email, username",
    [(DEV_EMAIL, "otra-persona"), ("otra@example.com", DEV_USERNAME.upper())],
)
def test_no_toca_una_cuenta_ajena(db, email, username):
    db.add(User(email=email, username=username, password_hash="hash-original"))
    db.commit()

    mensaje = create_dev_user(db, "123")

    assert "no se cambió nada" in mensaje
    assert contar(db) == 1
    assert db.scalar(select(User.password_hash)) == "hash-original"
