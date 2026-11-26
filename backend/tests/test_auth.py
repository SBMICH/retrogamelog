"""Registro, inicio de sesión y usuario actual (historia H1)."""

import base64
import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin

import jwt
import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser
from app.api.routes import auth as auth_routes
from app.core.security import DUMMY_PASSWORD_HASH
from app.main import app, create_app
from app.models import User

REGISTRO = "/api/v1/auth/register"
LOGIN = "/api/v1/auth/login"
YO = "/api/v1/me"

CLAVE = "contrasena-de-prueba-123"
ANA = {"email": "ana@example.com", "username": "ana", "password": CLAVE}
CAMPOS_USUARIO = {"id", "email", "username", "is_public", "created_at"}
SECRETO = app.state.auth_settings.jwt_secret


@pytest.fixture
def client(db):
    # Depende de db para que las tablas queden vacías al terminar cada test.
    return TestClient(app)


def registrar(client, **cambios):
    return client.post(REGISTRO, json={**ANA, **cambios})


def iniciar_sesion(client, email=ANA["email"], password=CLAVE):
    return client.post(LOGIN, data={"username": email, "password": password})


def contar_usuarios(db):
    return db.scalar(select(func.count()).select_from(User))


def con_token(token):
    return {"Authorization": f"Bearer {token}"}


def en_una_hora():
    return datetime.now(timezone.utc) + timedelta(hours=1)


# --- Registro ---------------------------------------------------------------------------------


def test_registro_responde_201_sin_contrasena_ni_hash(client):
    response = registrar(client)

    assert response.status_code == 201
    cuerpo = response.json()
    assert set(cuerpo) == CAMPOS_USUARIO
    assert cuerpo["email"] == "ana@example.com"
    assert cuerpo["username"] == "ana"
    assert cuerpo["is_public"] is False
    assert CLAVE not in response.text
    assert "argon2" not in response.text


def test_registro_guarda_el_email_en_minusculas_y_respeta_el_username(client, db):
    response = registrar(client, email="  Ana.Perez@Example.COM ", username="AnaPerez")

    assert response.status_code == 201
    assert response.json()["email"] == "ana.perez@example.com"
    usuario = db.scalar(select(User))
    assert usuario.email == "ana.perez@example.com"
    assert usuario.username == "AnaPerez"


def test_la_contrasena_se_guarda_solo_como_hash_argon2id(client, db):
    registrar(client)

    usuario = db.scalar(select(User))
    assert usuario.password_hash.startswith("$argon2id$")
    assert CLAVE not in usuario.password_hash
    assert PasswordHasher().verify(usuario.password_hash, CLAVE)


def test_registro_ignora_campos_que_no_le_corresponden(client):
    response = registrar(client, id=999, is_public=True, password_hash="x")

    assert response.status_code == 201
    assert response.json()["id"] != 999
    assert response.json()["is_public"] is False


@pytest.mark.parametrize("username", ["abc", "a" * 30, "Ana_Perez-99", "___", "123"])
def test_username_valido(client, username):
    # Una contraseña que no contiene ninguno de los nombres probados.
    assert registrar(client, username=username, password="Zq7-llave-segura").status_code == 201


@pytest.mark.parametrize(
    "username",
    ["", "ab", "a" * 31, "ana perez", " ana", "ana\n", "añ_a", "ana.perez", "ana@x", "ana\x00", 123, None],
)
def test_username_invalido(client, db, username):
    response = registrar(client, username=username)

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "username"]
    assert contar_usuarios(db) == 0


@pytest.mark.parametrize(
    "password", ["abcdefg1", "a" * 127 + "1", "a1" + " " * 6, "contraseña con ñ y € 7"]
)
def test_contrasena_valida_sirve_para_iniciar_sesion(client, password):
    assert registrar(client, password=password).status_code == 201
    assert iniciar_sesion(client, password=password).status_code == 200


@pytest.mark.parametrize("password", ["", "a" * 7, "a" * 129, 12345678, None])
def test_contrasena_invalida(client, db, password):
    response = registrar(client, password=password)

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "password"]
    assert contar_usuarios(db) == 0


@pytest.mark.parametrize(
    "email",
    [
        "",
        "sin-arroba",
        "ana@",
        "@example.com",
        "ana perez@example.com",
        "Ana <ana@example.com>",
        "ana@@example.com",
        "ana@localhost",
        "ana\x00@example.com",
        "a" * 250 + "@example.com",
        # Menos de 254 caracteres, pero más de 254 bytes (y más de 254 caracteres en minúsculas).
        "İ" * 60 + "@" + ".".join(["a" * 60] * 3) + ".com",
        123,
        None,
    ],
)
def test_email_invalido(client, db, email):
    response = registrar(client, email=email)

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "email"]
    assert contar_usuarios(db) == 0


def test_el_email_que_mas_crece_en_minusculas_cabe_en_la_columna(client, db):
    # "İ" pasa a ser dos caracteres en minúsculas: la dirección crece de 219 a 251.
    email = "İ" * 32 + "@" + ".".join(["a" * 60] * 3) + ".com"

    assert registrar(client, email=email).status_code == 201

    assert len(db.scalar(select(User.email))) == 251
    assert iniciar_sesion(client, email=email).status_code == 200


def test_un_email_desmesurado_se_descarta_antes_de_analizarlo(client):
    response = registrar(client, email="a" * 100_000 + "@example.com")

    assert response.status_code == 422
    assert response.json()["detail"][0]["type"] == "string_too_long"


@pytest.mark.parametrize("campo", ["email", "username", "password"])
def test_caracter_unicode_suelto_responde_422(client, db, campo):
    """JSON admite medio par sustituto, que no se puede convertir a bytes para guardarlo o hashearlo."""
    cuerpo = json.dumps({**ANA, campo: ANA[campo] + "\ud800"}).encode()

    response = client.post(REGISTRO, content=cuerpo, headers={"Content-Type": "application/json"})

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", campo]
    assert contar_usuarios(db) == 0


@pytest.mark.parametrize(
    "cambios, mensaje",
    [
        ({"email": "ana@example.com", "username": "otra"}, "El email ya está registrado."),
        ({"email": "ANA@Example.com", "username": "otra"}, "El email ya está registrado."),
        ({"email": "otra@example.com", "username": "ana"}, "El nombre de usuario ya está en uso."),
        ({"email": "otra@example.com", "username": "AnA"}, "El nombre de usuario ya está en uso."),
    ],
)
def test_registro_duplicado_responde_409(client, db, cambios, mensaje):
    registrar(client)

    response = registrar(client, **cambios)

    assert response.status_code == 409
    assert response.json() == {"detail": mensaje}
    assert contar_usuarios(db) == 1


@pytest.mark.parametrize(
    "segundo, mensaje",
    [
        ({"email": "ANA@example.com", "username": "otra"}, "El email ya está registrado."),
        ({"email": "otra@example.com", "username": "ANA"}, "El nombre de usuario ya está en uso."),
    ],
)
def test_dos_registros_simultaneos_uno_201_y_otro_409(db, monkeypatch, segundo, mensaje):
    # La barrera retiene a los dos hasta que ambos están a punto de insertar.
    barrera = threading.Barrier(2, timeout=15)
    hash_original = auth_routes.hash_password

    def hash_sincronizado(password):
        resultado = hash_original(password)
        barrera.wait()
        return resultado

    monkeypatch.setattr(auth_routes, "hash_password", hash_sincronizado)

    with ThreadPoolExecutor(max_workers=2) as pool:
        respuestas = list(
            pool.map(lambda cuerpo: TestClient(app).post(REGISTRO, json=cuerpo), [ANA, {**ANA, **segundo}])
        )

    assert sorted(r.status_code for r in respuestas) == [201, 409]
    perdedor = next(r for r in respuestas if r.status_code == 409)
    assert perdedor.json() == {"detail": mensaje}
    assert contar_usuarios(db) == 1


def test_otro_error_de_integridad_no_se_disfraza_de_409(client, monkeypatch):
    class OtraRestriccion(Exception):
        class diag:
            constraint_name = "ck_users_otra"

    def commit_que_falla(self):
        raise IntegrityError("INSERT", {}, OtraRestriccion())

    monkeypatch.setattr(Session, "commit", commit_que_falla)

    with pytest.raises(IntegrityError):
        registrar(client)


# --- Los errores 422 no devuelven la entrada --------------------------------------------------

SECRETA = "Zq9#valor-secreto"


@pytest.mark.parametrize(
    "peticion",
    [
        pytest.param({"json": {**ANA, "password": "Zq9#vs"}}, id="contrasena-corta"),
        pytest.param({"json": {**ANA, "password": SECRETA * 10}}, id="contrasena-larga"),
        pytest.param({"json": {**ANA, "password": [SECRETA]}}, id="contrasena-lista"),
        pytest.param({"json": {**ANA, "password": {"v": SECRETA}}}, id="contrasena-objeto"),
        pytest.param({"json": {**ANA, "email": "mal", "password": SECRETA}}, id="email-malo"),
        pytest.param({"json": {**ANA, "username": "x", "password": SECRETA}}, id="username-malo"),
        pytest.param({"json": {**ANA, "email": SECRETA}}, id="contrasena-en-email"),
        pytest.param({"json": {**ANA, "username": SECRETA}}, id="contrasena-en-username"),
        pytest.param({"json": {"password": SECRETA}}, id="faltan-campos"),
        pytest.param({"json": [SECRETA]}, id="cuerpo-lista"),
        pytest.param({"json": SECRETA}, id="cuerpo-texto"),
        pytest.param({"data": {**ANA, "password": SECRETA}}, id="formulario-en-vez-de-json"),
        pytest.param(
            {"content": SECRETA.encode(), "headers": {"Content-Type": "text/plain"}},
            id="texto-plano",
        ),
        pytest.param(
            {
                "content": ('{"password": "' + SECRETA + '",').encode(),
                "headers": {"Content-Type": "application/json"},
            },
            id="json-roto",
        ),
        pytest.param(
            {
                "content": (
                    '{"email": "ana@example.com", "username": "ana", "password": "'
                    + SECRETA
                    + '\\ud800"}'
                ).encode(),
                "headers": {"Content-Type": "application/json"},
            },
            id="caracter-suelto",
        ),
    ],
)
def test_422_del_registro_no_devuelve_la_contrasena(client, db, peticion):
    response = client.post(REGISTRO, **peticion)

    assert response.status_code == 422
    assert "Zq9" not in response.text
    assert all(set(error) == {"type", "loc", "msg"} for error in response.json()["detail"])
    assert contar_usuarios(db) == 0


@pytest.mark.parametrize(
    "formulario",
    [
        {"password": SECRETA},
        {"username": SECRETA},
        {"username": "ana@example.com", "password": SECRETA, "grant_type": "otro"},
    ],
)
def test_422_del_login_no_devuelve_la_entrada(client, formulario):
    response = client.post(LOGIN, data=formulario)

    assert response.status_code == 422
    assert "Zq9" not in response.text
    assert all(set(error) == {"type", "loc", "msg"} for error in response.json()["detail"])


# --- Inicio de sesión -------------------------------------------------------------------------


@pytest.mark.parametrize("email", ["ana@example.com", "ANA@Example.COM", " ana@example.com "])
def test_login_devuelve_token_bearer(client, email):
    registrar(client)

    response = iniciar_sesion(client, email=email)

    assert response.status_code == 200
    assert set(response.json()) == {"access_token", "token_type"}
    assert response.json()["token_type"] == "bearer"
    assert response.json()["access_token"].count(".") == 2


def test_login_normaliza_el_email_igual_que_el_registro(client):
    compuesta = "josé@example.com"
    descompuesta = "josé@example.com"
    assert registrar(client, email=compuesta).status_code == 201

    assert iniciar_sesion(client, email=descompuesta).status_code == 200


@pytest.mark.parametrize(
    "email, password",
    [
        pytest.param("ana@example.com", "contrasena-equivocada", id="contrasena-incorrecta"),
        pytest.param("nadie@example.com", CLAVE, id="email-desconocido"),
        pytest.param("ana", CLAVE, id="username-en-vez-de-email"),
        pytest.param("no es un email", CLAVE, id="email-mal-formado"),
        pytest.param("ana\x00@example.com", CLAVE, id="byte-nulo"),
        pytest.param("a" * 5000 + "@example.com", CLAVE, id="email-enorme"),
        pytest.param("' OR 1=1 --", CLAVE, id="inyeccion"),
        pytest.param("ana@example.com", "a" * 5000, id="contrasena-enorme"),
        pytest.param("ana@example.com", CLAVE.upper(), id="mayusculas-en-contrasena"),
    ],
)
def test_login_fallido_responde_siempre_igual(client, email, password):
    registrar(client)

    response = iniciar_sesion(client, email=email, password=password)

    assert response.status_code == 401
    assert response.json() == {"detail": "Email o contraseña incorrectos."}
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize(
    "email", ["nadie@example.com", "no es un email", "ana\x00@example.com"]
)
def test_login_con_email_inexistente_tambien_verifica_un_hash(client, monkeypatch, email):
    """Sin esto, un email desconocido respondería mucho antes y delataría qué cuentas existen."""
    registrar(client)
    verificaciones = []
    original = auth_routes.verify_password

    def espia(password_hash, password):
        verificaciones.append(password_hash)
        return original(password_hash, password)

    monkeypatch.setattr(auth_routes, "verify_password", espia)

    iniciar_sesion(client, email=email)

    assert verificaciones == [DUMMY_PASSWORD_HASH]


@pytest.mark.parametrize("email", ["ana@example.com", "nadie@example.com"])
def test_login_no_calcula_hashes_de_contrasenas_mas_largas_que_el_maximo(client, monkeypatch, email):
    registrar(client)
    verificaciones = []
    monkeypatch.setattr(auth_routes, "verify_password", lambda *args: verificaciones.append(args))

    response = iniciar_sesion(client, email=email, password="a" * 129)

    assert response.status_code == 401
    assert verificaciones == []


def test_el_hash_de_relleno_cuesta_lo_mismo_que_uno_real(client, db):
    registrar(client)
    real = db.scalar(select(User.password_hash))

    # "$argon2id$v=19$m=...,t=...,p=..." : mismo algoritmo y mismos parámetros de coste.
    assert DUMMY_PASSWORD_HASH.split("$")[:4] == real.split("$")[:4]
    assert len(DUMMY_PASSWORD_HASH) == len(real)


# --- Token ------------------------------------------------------------------------------------


def test_el_token_usa_hs256_identifica_al_usuario_y_caduca_a_la_hora(client):
    usuario_id = registrar(client).json()["id"]
    antes = datetime.now(timezone.utc).timestamp()

    token = iniciar_sesion(client).json()["access_token"]

    assert jwt.get_unverified_header(token)["alg"] == "HS256"
    datos = jwt.decode(token, SECRETO, algorithms=["HS256"])
    assert set(datos) == {"sub", "exp"}
    assert datos["sub"] == str(usuario_id)
    assert antes + 3600 - 5 <= datos["exp"] <= antes + 3600 + 30


def test_la_caducidad_configurada_se_aplica_al_token(client, monkeypatch):
    registrar(client)
    monkeypatch.setenv("ACCESS_TOKEN_EXPIRE_MINUTES", "5")
    otra = TestClient(create_app())
    antes = datetime.now(timezone.utc).timestamp()

    token = iniciar_sesion(otra).json()["access_token"]

    datos = jwt.decode(token, SECRETO, algorithms=["HS256"])
    assert antes + 300 - 5 <= datos["exp"] <= antes + 300 + 30


# --- Usuario actual ---------------------------------------------------------------------------


def assert_no_autenticado(response):
    assert response.status_code == 401
    assert response.json() == {"detail": "No se pudo validar la autenticación."}
    assert response.headers["www-authenticate"] == "Bearer"


def test_me_devuelve_los_datos_propios(client):
    ana = registrar(client).json()
    luis = registrar(client, email="luis@example.com", username="luis").json()
    token_ana = iniciar_sesion(client).json()["access_token"]
    token_luis = iniciar_sesion(client, email="luis@example.com").json()["access_token"]

    respuesta_ana = client.get(YO, headers=con_token(token_ana))
    respuesta_luis = client.get(YO, headers=con_token(token_luis))

    assert respuesta_ana.status_code == 200
    assert respuesta_ana.json() == ana
    assert respuesta_luis.json() == luis
    assert set(respuesta_ana.json()) == CAMPOS_USUARIO


def test_un_token_correcto_hecho_a_mano_es_aceptado(client):
    """Control de los tests de abajo: solo falla el detalle que cambia cada uno."""
    usuario_id = registrar(client).json()["id"]
    token = jwt.encode({"sub": str(usuario_id), "exp": en_una_hora()}, SECRETO, algorithm="HS256")

    assert client.get(YO, headers=con_token(token)).status_code == 200


@pytest.mark.parametrize(
    "cabeceras",
    [
        {},
        {"Authorization": ""},
        {"Authorization": "Bearer"},
        {"Authorization": "Bearer "},
        {"Authorization": "Basic YW5hOmNsYXZl"},
        {"Authorization": "Bearer no-es-un-token"},
        {"Authorization": "Bearer a.b.c"},
        {"Authorization": "Bearer " + "A" * 5000},
        {"Authorization": b"Bearer \xe9.\xe9.\xe9"},
    ],
)
def test_me_sin_token_o_mal_formado(client, cabeceras):
    registrar(client)

    assert_no_autenticado(client.get(YO, headers=cabeceras))


def test_me_con_token_sin_el_prefijo_bearer(client):
    registrar(client)
    token = iniciar_sesion(client).json()["access_token"]

    assert_no_autenticado(client.get(YO, headers={"Authorization": token}))


def test_me_con_firma_de_otro_secreto(client):
    usuario_id = registrar(client).json()["id"]
    token = jwt.encode({"sub": str(usuario_id), "exp": en_una_hora()}, "o" * 40, algorithm="HS256")

    assert_no_autenticado(client.get(YO, headers=con_token(token)))


def test_me_con_contenido_alterado(client):
    registrar(client)
    luis = registrar(client, email="luis@example.com", username="luis").json()["id"]
    cabecera, _, firma = iniciar_sesion(client).json()["access_token"].split(".")
    falso = json.dumps({"sub": str(luis), "exp": int(en_una_hora().timestamp())}).encode()
    cuerpo = base64.urlsafe_b64encode(falso).rstrip(b"=").decode()

    assert_no_autenticado(client.get(YO, headers=con_token(f"{cabecera}.{cuerpo}.{firma}")))


@pytest.mark.parametrize("algoritmo", ["HS384", "HS512"])
def test_me_rechaza_otro_algoritmo_aunque_use_el_mismo_secreto(client, monkeypatch, algoritmo):
    # Secreto largo: válido también para HS384 y HS512, así la única diferencia es el algoritmo.
    secreto = "k" * 64
    monkeypatch.setenv("JWT_SECRET", secreto)
    cliente = TestClient(create_app())
    datos = {"sub": str(registrar(client).json()["id"]), "exp": en_una_hora()}
    correcto = jwt.encode(datos, secreto, algorithm="HS256")
    otro = jwt.encode(datos, secreto, algorithm=algoritmo)

    assert cliente.get(YO, headers=con_token(correcto)).status_code == 200
    assert_no_autenticado(cliente.get(YO, headers=con_token(otro)))


def test_me_rechaza_un_token_sin_firma(client):
    usuario_id = registrar(client).json()["id"]
    token = jwt.encode({"sub": str(usuario_id), "exp": en_una_hora()}, None, algorithm="none")

    assert_no_autenticado(client.get(YO, headers=con_token(token)))


def test_me_con_token_caducado(client):
    usuario_id = registrar(client).json()["id"]
    hace_un_rato = datetime.now(timezone.utc) - timedelta(seconds=5)
    token = jwt.encode({"sub": str(usuario_id), "exp": hace_un_rato}, SECRETO, algorithm="HS256")

    assert_no_autenticado(client.get(YO, headers=con_token(token)))


@pytest.mark.parametrize("falta", ["exp", "sub"])
def test_me_exige_exp_y_sub(client, falta):
    usuario_id = registrar(client).json()["id"]
    datos = {"sub": str(usuario_id), "exp": en_una_hora()}
    del datos[falta]
    token = jwt.encode(datos, SECRETO, algorithm="HS256")

    assert_no_autenticado(client.get(YO, headers=con_token(token)))


@pytest.mark.parametrize(
    "sub", ["", "0", "-1", "abc", "1.0", " 1", "1\n", "01", "١", "²", "9" * 30, "2147483648", None]
)
def test_me_con_sub_que_no_es_un_id(client, sub):
    assert registrar(client).json()["id"] == 1
    token = jwt.encode({"sub": sub, "exp": en_una_hora()}, SECRETO, algorithm="HS256")

    assert_no_autenticado(client.get(YO, headers=con_token(token)))


def test_me_con_usuario_que_ya_no_existe(client, db):
    registrar(client)
    token = iniciar_sesion(client).json()["access_token"]
    db.delete(db.scalar(select(User)))
    db.commit()

    assert_no_autenticado(client.get(YO, headers=con_token(token)))


def test_la_dependencia_de_usuario_actual_sirve_para_otras_rutas(client):
    otra = create_app()

    @otra.get("/api/v1/me/prueba")
    def prueba(user: CurrentUser) -> dict[str, int]:
        return {"user_id": user.id}

    usuario_id = registrar(client).json()["id"]
    token = iniciar_sesion(client).json()["access_token"]
    cliente = TestClient(otra)

    assert_no_autenticado(cliente.get("/api/v1/me/prueba"))
    assert cliente.get("/api/v1/me/prueba", headers=con_token(token)).json() == {"user_id": usuario_id}


# --- Documentación interactiva y registros ----------------------------------------------------


def test_authorize_de_docs_apunta_al_login(client):
    esquema = client.get("/openapi.json").json()

    (nombre, seguridad), = esquema["components"]["securitySchemes"].items()
    assert seguridad["type"] == "oauth2"
    # Swagger resuelve la URL relativa a la página /docs.
    assert urljoin("http://servidor/docs", seguridad["flows"]["password"]["tokenUrl"]) == (
        "http://servidor" + LOGIN
    )
    assert esquema["paths"][YO]["get"]["security"] == [{nombre: []}]
    assert "application/x-www-form-urlencoded" in esquema["paths"][LOGIN]["post"]["requestBody"]["content"]


def test_login_acepta_la_peticion_que_envia_authorize(client):
    registrar(client)

    response = client.post(
        LOGIN,
        data={"grant_type": "password", "username": ANA["email"], "password": CLAVE},
        headers={"Authorization": "Basic Og==", "X-Requested-With": "XMLHttpRequest"},
    )

    assert response.status_code == 200


def test_ni_contrasenas_ni_tokens_ni_hashes_en_los_registros(client, db, caplog, capsys):
    caplog.set_level(logging.DEBUG)
    # SQLAlchemy en INFO anota cada consulta; ahí se ven los parámetros si no se ocultan. Su nivel
    # DEBUG imprime además las filas leídas (con el hash): no debe activarse fuera de una depuración.
    caplog.set_level(logging.INFO, logger="sqlalchemy.engine")

    registrar(client)
    registrar(client)
    registrar(client, password="Zq9#ab")
    iniciar_sesion(client, password="contrasena-equivocada")
    token = iniciar_sesion(client).json()["access_token"]
    client.get(YO, headers=con_token(token))
    client.get(YO, headers=con_token(token + "x"))

    salida = capsys.readouterr()
    registros = caplog.text + salida.out + salida.err
    assert "INSERT INTO users" in registros  # los registros de SQL sí se capturaron
    hash_guardado = db.scalar(select(User.password_hash))
    for prohibido in (CLAVE, "contrasena-equivocada", "Zq9#ab", token, hash_guardado, "$argon2"):
        assert prohibido not in registros
