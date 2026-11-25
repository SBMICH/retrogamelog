import pytest
from fastapi.testclient import TestClient

from app.core.config import DEFAULT_CORS_ORIGINS, get_cors_origins
from app.main import app, create_app

ORIGEN_PERMITIDO = DEFAULT_CORS_ORIGINS[0]
ORIGEN_DESCONOCIDO = "https://sitio-malicioso.example"

client = TestClient(app)


def test_origen_permitido_recibe_la_cabecera():
    response = client.get("/health", headers={"Origin": ORIGEN_PERMITIDO})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ORIGEN_PERMITIDO


def test_origen_desconocido_no_recibe_la_cabecera():
    response = client.get("/health", headers={"Origin": ORIGEN_DESCONOCIDO})

    assert "access-control-allow-origin" not in response.headers


def test_peticion_previa_de_origen_permitido_es_aceptada():
    response = client.options(
        "/health",
        headers={
            "Origin": ORIGEN_PERMITIDO,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ORIGEN_PERMITIDO
    assert "authorization" in response.headers["access-control-allow-headers"].lower()


def test_peticion_previa_de_origen_desconocido_es_rechazada():
    response = client.options(
        "/health",
        headers={
            "Origin": ORIGEN_DESCONOCIDO,
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_no_se_permiten_credenciales_entre_origenes():
    response = client.get("/health", headers={"Origin": ORIGEN_PERMITIDO})

    assert "access-control-allow-credentials" not in response.headers


def test_sin_variable_se_usan_los_origenes_de_desarrollo(monkeypatch):
    monkeypatch.delenv("CORS_ORIGINS", raising=False)

    assert get_cors_origins() == DEFAULT_CORS_ORIGINS


def test_origenes_configurados_reemplazan_a_los_de_desarrollo(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "https://retrogamelog.example, https://otro.example/")
    otra_app = TestClient(create_app())

    permitido = otra_app.get("/health", headers={"Origin": "https://retrogamelog.example"})
    por_defecto = otra_app.get("/health", headers={"Origin": ORIGEN_PERMITIDO})

    assert get_cors_origins() == ["https://retrogamelog.example", "https://otro.example"]
    assert permitido.headers["access-control-allow-origin"] == "https://retrogamelog.example"
    assert "access-control-allow-origin" not in por_defecto.headers


def test_variable_vacia_no_permite_ningun_origen(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "")
    otra_app = TestClient(create_app())

    response = otra_app.get("/health", headers={"Origin": ORIGEN_PERMITIDO})

    assert get_cors_origins() == []
    assert "access-control-allow-origin" not in response.headers


def test_el_comodin_esta_prohibido(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "https://retrogamelog.example,*")

    with pytest.raises(RuntimeError, match=r"\*"):
        get_cors_origins()


@pytest.mark.parametrize("valor", ["localhost:5173", "ftp://servidor.example", "retrogamelog.example"])
def test_origenes_mal_escritos_se_rechazan(monkeypatch, valor):
    monkeypatch.setenv("CORS_ORIGINS", valor)

    with pytest.raises(RuntimeError, match="inválido"):
        get_cors_origins()
