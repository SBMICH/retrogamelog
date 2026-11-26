"""Reglas de las contraseñas nuevas."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.password_policy import COMMON_PASSWORDS, password_problem
from app.core.security import hash_password
from app.main import app
from app.models import User

REGISTRO = "/api/v1/auth/register"
LOGIN = "/api/v1/auth/login"


@pytest.fixture
def client(db):
    return TestClient(app)


def registrar(client, password, username="marta", email="marta.rios@example.com"):
    return client.post(
        REGISTRO, json={"email": email, "username": username, "password": password}
    )


@pytest.mark.parametrize(
    "password, motivo",
    [
        pytest.param("abcdefghij", "una letra y un número", id="sin-numero"),
        pytest.param("9876501234", "una letra y un número", id="sin-letra"),
        pytest.param("!!!???...,,,", "una letra y un número", id="solo-simbolos"),
        pytest.param("password123", "demasiado común", id="comun"),
        pytest.param("PassWord123", "demasiado común", id="comun-con-mayusculas"),
        pytest.param("zz-MARTA-2026", "nombre de usuario", id="contiene-usuario"),
        pytest.param("zz-Marta.Rios-7", "nombre de usuario", id="usuario-dentro-del-correo"),
    ],
)
def test_el_registro_rechaza_contrasenas_debiles(client, db, password, motivo):
    response = registrar(client, password)

    assert response.status_code == 422
    error = response.json()["detail"][0]
    assert error["loc"] == ["body", "password"]
    assert motivo in error["msg"]
    assert password not in response.text
    assert db.scalar(select(func.count()).select_from(User)) == 0


def test_el_registro_rechaza_la_parte_local_del_correo(client):
    response = registrar(client, "zz-rios77-llave", username="otra", email="rios77@example.com")

    assert response.status_code == 422
    assert "tu correo" in response.json()["detail"][0]["msg"]


def test_la_contrasena_123_se_rechaza_en_el_registro(client):
    assert registrar(client, "123").status_code == 422


def test_una_contrasena_razonable_se_acepta(client):
    assert registrar(client, "retro-llave-42").status_code == 201


@pytest.mark.parametrize(
    "password",
    [
        pytest.param("zz-josé-1234", id="compuesta"),
        pytest.param("zz-josé-1234", id="descompuesta"),
    ],
)
def test_los_datos_personales_se_detectan_en_cualquier_forma_unicode(password):
    assert "tu correo" in password_problem(password, "otra", "josé@example.com")


@pytest.mark.parametrize("password", ["abcdefg²", "abcdefgh①"])
def test_un_superindice_no_cuenta_como_numero(password):
    assert "una letra y un número" in password_problem(password, None, None)


def test_los_datos_personales_muy_cortos_no_cuentan():
    assert password_problem("llave-jo-2468", "otra", "jo@example.com") is None


def test_la_lista_de_comunes_se_carga_sin_comentarios():
    assert "password123" in COMMON_PASSWORDS
    assert not any(item.startswith("#") for item in COMMON_PASSWORDS)


def test_toda_contrasena_comun_de_la_lista_se_rechaza():
    for common in COMMON_PASSWORDS:
        assert password_problem(common, None, None) is not None


def test_el_inicio_de_sesion_no_aplica_las_reglas(client, db):
    """Una cuenta anterior a las reglas (o el usuario de desarrollo) puede seguir entrando."""
    db.add(User(email="vieja@example.com", username="vieja", password_hash=hash_password("123")))
    db.commit()

    response = client.post(LOGIN, data={"username": "vieja@example.com", "password": "123"})

    assert response.status_code == 200
