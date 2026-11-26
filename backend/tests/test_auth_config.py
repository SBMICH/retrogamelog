"""Configuración de la autenticación: lo que se comprueba al arrancar."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.core.config import get_auth_settings
from app.main import create_app

BACKEND = Path(__file__).resolve().parent.parent
SECRETO_VALIDO = "s" * 32


@pytest.fixture(autouse=True)
def entorno_conocido(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", SECRETO_VALIDO)
    monkeypatch.delenv("ACCESS_TOKEN_EXPIRE_MINUTES", raising=False)


def test_secreto_de_longitud_minima_y_caducidad_por_defecto():
    settings = get_auth_settings()

    assert settings.jwt_secret == SECRETO_VALIDO
    assert settings.access_token_expire_minutes == 60
    assert create_app().state.auth_settings == settings


@pytest.mark.parametrize("funcion", [get_auth_settings, create_app])
def test_sin_jwt_secret_no_arranca(monkeypatch, funcion):
    monkeypatch.delenv("JWT_SECRET")

    with pytest.raises(RuntimeError, match="Falta la variable de entorno JWT_SECRET"):
        funcion()


@pytest.mark.parametrize("secreto", ["", "abc123xyz", "s" * 31," " * 40, "  " + "s" * 31 + "  "])
@pytest.mark.parametrize("funcion", [get_auth_settings, create_app])
def test_jwt_secret_corto_no_arranca(monkeypatch, funcion, secreto):
    monkeypatch.setenv("JWT_SECRET", secreto)

    with pytest.raises(RuntimeError, match="al menos 32 caracteres") as error:
        funcion()

    if secreto.strip():
        assert secreto.strip() not in str(error.value)


def test_importar_la_aplicacion_sin_secreto_falla():
    """Es lo que hace uvicorn al arrancar. Se usa otro proceso para empezar sin nada importado."""
    entorno = {k: v for k, v in os.environ.items() if k != "JWT_SECRET"}

    resultado = subprocess.run(
        [sys.executable, "-c", "import app.main"],
        cwd=BACKEND,
        env=entorno,
        capture_output=True,
        timeout=60,
    )

    assert resultado.returncode != 0
    assert b"JWT_SECRET" in resultado.stderr


def test_el_secreto_no_aparece_al_imprimir_la_configuracion():
    assert SECRETO_VALIDO not in repr(get_auth_settings())


@pytest.mark.parametrize("valor, minutos", [("1", 1), ("15", 15), ("10080", 10080)])
def test_caducidad_configurable(monkeypatch, valor, minutos):
    monkeypatch.setenv("ACCESS_TOKEN_EXPIRE_MINUTES", valor)

    assert get_auth_settings().access_token_expire_minutes == minutos


@pytest.mark.parametrize("valor", ["0", "-5", "10081", "sesenta", "1.5", ""])
def test_caducidad_invalida_no_arranca(monkeypatch, valor):
    monkeypatch.setenv("ACCESS_TOKEN_EXPIRE_MINUTES", valor)

    with pytest.raises(RuntimeError, match="ACCESS_TOKEN_EXPIRE_MINUTES"):
        create_app()
