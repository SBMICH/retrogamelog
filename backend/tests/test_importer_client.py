import logging
import traceback
from dataclasses import fields
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

import httpx
import pytest

from app.importers.client import (
    RemoteGame,
    RetroAchievementsClient,
    RetroAchievementsError,
)
from app.importers.consoles import (
    DEFAULT_CONSOLES,
    Console,
    ConsoleSelectionError,
    select_consoles,
)
from app.importers.settings import get_importer_settings
from importer_fakes import (  # noqa: F401  (sin_red es una fixture autouse)
    CONSOLES,
    FAKE_KEY,
    FakeApi,
    FakeTime,
    game,
    sin_red,
)


def make_client(api: FakeApi, time: FakeTime | None = None, key: str = FAKE_KEY):
    time = time or FakeTime()
    return RetroAchievementsClient(key, transport=api.transport, sleep=time.sleep, clock=time.clock)


def full_report(error: BaseException) -> str:
    """Todo lo que un registro de errores podría mostrar de una excepción."""
    return "".join([str(error), repr(error), *traceback.format_exception(error)])


# --- Ajustes ---


def test_lee_la_clave_de_la_variable_de_entorno(monkeypatch):
    monkeypatch.setenv("RETROACHIEVEMENTS_API_KEY", f"  {FAKE_KEY}\n")
    assert get_importer_settings().api_key == FAKE_KEY


@pytest.mark.parametrize("value", [None, "", "   "])
def test_sin_clave_falla_nombrando_la_variable(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("RETROACHIEVEMENTS_API_KEY", raising=False)
    else:
        monkeypatch.setenv("RETROACHIEVEMENTS_API_KEY", value)
    with pytest.raises(RuntimeError, match="RETROACHIEVEMENTS_API_KEY"):
        get_importer_settings()


def test_la_clave_no_aparece_al_imprimir_los_ajustes(monkeypatch):
    monkeypatch.setenv("RETROACHIEVEMENTS_API_KEY", FAKE_KEY)
    settings = get_importer_settings()
    assert FAKE_KEY not in repr(settings)
    assert FAKE_KEY not in str(settings)


# --- Peticiones y respuestas ---


def test_pide_las_consolas_como_indica_la_documentacion():
    api = FakeApi()
    with make_client(api) as client:
        consoles = client.get_consoles()

    url = api.requests[0].url
    assert url.scheme == "https"
    assert url.host == "retroachievements.org"
    assert url.path == "/API/API_GetConsoleIDs.php"
    assert dict(url.params) == {"y": FAKE_KEY, "g": "1"}
    assert consoles[0] == Console(id=101, name="Genesis/Mega Drive")
    assert len(consoles) == len(CONSOLES)


def test_pide_la_lista_de_juegos_sin_hashes_ni_paginacion():
    api = FakeApi()
    with make_client(api) as client:
        client.get_games(103)

    assert len(api.requests) == 1
    url = api.requests[0].url
    assert url.path == "/API/API_GetGameList.php"
    # Solo clave y consola: ni "h" (hashes) ni "o"/"c".
    assert dict(url.params) == {"y": FAKE_KEY, "i": "103"}


def test_de_cada_juego_solo_conserva_id_titulo_e_icono():
    api = FakeApi(games={103: [game(7, "  Super Juego \u0000", 103, "/Images/000007.png")]})
    with make_client(api) as client:
        games = client.get_games(103)

    # Aunque la respuesta traiga hashes, no hay dónde guardarlos.
    assert [f.name for f in fields(RemoteGame)] == ["id", "title", "icon_url"]
    assert games == [
        RemoteGame(
            id=7,
            title="Super Juego",
            icon_url="https://media.retroachievements.org/Images/000007.png",
        )
    ]


@pytest.mark.parametrize(
    "icon",
    [
        "",
        "https://example.com/rom.zip",
        "//example.com/Images/1.png",
        "/Images/../roms/juego.sfc",
        "/roms/juego.sfc",
        "/Images/1.zip",
        "/Images/1.png?x=1",
        "/Images/" + "1" * 600 + ".png",
        123,
    ],
)
def test_solo_acepta_iconos_con_la_ruta_documentada(icon):
    api = FakeApi(games={103: [{"ID": 1, "Title": "Juego", "ImageIcon": icon}]})
    with make_client(api) as client:
        assert client.get_games(103)[0].icon_url is None


def test_recorta_textos_demasiado_largos():
    api = FakeApi(
        consoles=[{"ID": 1, "Name": "c" * 150}], games={103: [game(1, "t" * 300, 103)]}
    )
    with make_client(api) as client:
        assert client.get_consoles()[0].name == "c" * 100
        assert client.get_games(103)[0].title == "t" * 255


def test_un_juego_repetido_en_la_respuesta_cuenta_una_vez():
    api = FakeApi(games={103: [game(1, "Primero", 103), game(1, "Repetido", 103)]})
    with make_client(api) as client:
        assert [g.title for g in client.get_games(103)] == ["Primero"]


@pytest.mark.parametrize(
    "body",
    [
        {"success": False},
        "texto",
        [None],
        [{"Title": "Sin ID"}],
        [{"ID": "1", "Title": "ID de texto"}],
        [{"ID": True, "Title": "ID booleano"}],
        [{"ID": 0, "Title": "ID cero"}],
        [{"ID": 1}],
        [{"ID": 1, "Title": "   "}],
        [{"id": 1, "title": "Formato de otra librería"}],
        [{"ID": 1, "Title": "De otra consola", "ConsoleID": 999}],
    ],
)
def test_rechaza_respuestas_que_no_cumplen_el_formato(body):
    api = FakeApi(games={103: body})
    with make_client(api) as client, pytest.raises(RetroAchievementsError):
        client.get_games(103)
    assert len(api.requests) == 1


def test_rechaza_una_consola_sin_nombre():
    api = FakeApi(consoles=[{"ID": 1}])
    with make_client(api) as client, pytest.raises(RetroAchievementsError, match="Name"):
        client.get_consoles()


# --- Pausa y reintentos ---


def test_pausa_entre_llamadas():
    api, time = FakeApi(), FakeTime()
    with make_client(api, time) as client:
        client.get_consoles()
        assert time.sleeps == []
        client.get_games(103)
        assert time.sleeps == [1.0]
        time.now += 0.25
        client.get_games(105)
        assert time.sleeps == [1.0, 0.75]
        time.now += 5
        client.get_games(107)
        assert time.sleeps == [1.0, 0.75]


@pytest.mark.parametrize("status", [408, 429, 500, 502, 503, 504, 520, 524])
def test_reintenta_los_errores_http_temporales(status):
    api, time = FakeApi(), FakeTime()
    api.failures["consoles"] = [httpx.Response(status), httpx.Response(status)]
    with make_client(api, time) as client:
        assert client.get_consoles()

    assert len(api.requests) == 3
    assert time.sleeps == [2.0, 4.0]


@pytest.mark.parametrize(
    "error",
    [httpx.ConnectError, httpx.ReadTimeout, httpx.ReadError, httpx.RemoteProtocolError],
)
def test_reintenta_los_errores_de_red(error):
    api = FakeApi()
    api.failures["consoles"] = [error("fallo")]
    with make_client(api) as client:
        assert client.get_consoles()
    assert len(api.requests) == 2


@pytest.mark.parametrize("failure", [httpx.Response(503), httpx.ConnectTimeout("fallo")])
def test_los_reintentos_son_limitados(failure):
    api, time = FakeApi(), FakeTime()
    api.failures["consoles"] = [failure] * 20
    with make_client(api, time) as client:
        with pytest.raises(RetroAchievementsError, match="tras 4 intentos"):
            client.get_consoles()

    assert len(api.requests) == 4
    assert time.sleeps == [2.0, 4.0, 8.0]


@pytest.mark.parametrize("status", [301, 302, 400, 401, 403, 404, 422, 501])
def test_no_reintenta_los_errores_definitivos(status):
    api, time = FakeApi(), FakeTime()
    response = httpx.Response(status, headers={"Location": "https://example.com/"})
    api.failures["consoles"] = [response]
    with make_client(api, time) as client:
        with pytest.raises(RetroAchievementsError, match=str(status)):
            client.get_consoles()

    assert len(api.requests) == 1
    assert time.sleeps == []


@pytest.mark.parametrize("status", [401, 403])
def test_un_rechazo_de_acceso_sugiere_revisar_la_clave(status):
    api = FakeApi()
    api.failures["consoles"] = [httpx.Response(status)]
    with make_client(api) as client:
        with pytest.raises(RetroAchievementsError, match="revisa la clave"):
            client.get_consoles()


def test_no_reintenta_una_respuesta_que_no_es_json():
    api = FakeApi()
    api.failures["consoles"] = [httpx.Response(200, text="<html>mantenimiento</html>")]
    with make_client(api) as client:
        with pytest.raises(RetroAchievementsError, match="no es una lista JSON"):
            client.get_consoles()
    assert len(api.requests) == 1


def test_respeta_retry_after_en_segundos():
    api, time = FakeApi(), FakeTime()
    api.failures["consoles"] = [httpx.Response(429, headers={"Retry-After": "30"})]
    with make_client(api, time) as client:
        client.get_consoles()
    assert time.sleeps == [30.0]


def test_respeta_retry_after_con_fecha():
    api, time = FakeApi(), FakeTime()
    when = datetime.now(timezone.utc) + timedelta(seconds=60)
    header = format_datetime(when, usegmt=True)
    api.failures["consoles"] = [httpx.Response(503, headers={"Retry-After": header})]
    with make_client(api, time) as client:
        client.get_consoles()
    assert len(time.sleeps) == 1
    assert 50 < time.sleeps[0] <= 60


@pytest.mark.parametrize("header", ["0", "pronto", "-5", "Wed, 21 Oct 2015 07:28:00"])
def test_un_retry_after_corto_o_ilegible_no_reduce_la_espera(header):
    api, time = FakeApi(), FakeTime()
    api.failures["consoles"] = [httpx.Response(429, headers={"Retry-After": header})]
    with make_client(api, time) as client:
        client.get_consoles()
    assert time.sleeps == [2.0]


def test_si_la_api_pide_esperar_demasiado_se_abandona():
    api, time = FakeApi(), FakeTime()
    api.failures["consoles"] = [httpx.Response(429, headers={"Retry-After": "3600"})]
    with make_client(api, time) as client:
        with pytest.raises(RetroAchievementsError, match="3600 segundos"):
            client.get_consoles()
    assert len(api.requests) == 1
    assert time.sleeps == []


# --- La clave no se filtra ---


def leaking_failures():
    url = f"https://retroachievements.org/API/API_GetConsoleIDs.php?y={FAKE_KEY}"
    return [
        httpx.Response(401, text=url),
        httpx.Response(404, text=url),
        httpx.Response(500, text=url),
        httpx.Response(302, headers={"Location": url}),
        httpx.Response(200, text=url),
        httpx.Response(200, json={"error": url}),
        httpx.ConnectError(f"no se pudo conectar a {url}"),
        httpx.ReadTimeout(f"tiempo agotado en {url}"),
        httpx.ProxyError(f"proxy rechazó {url}"),
        RuntimeError(f"fallo inesperado en {url}"),
    ]


@pytest.mark.parametrize("failure", leaking_failures(), ids=repr)
def test_la_clave_no_aparece_en_errores_ni_registros(caplog, failure):
    caplog.set_level(logging.DEBUG)
    api = FakeApi()
    api.failures["consoles"] = [failure] * 4
    with make_client(api) as client:
        with pytest.raises(RetroAchievementsError) as caught:
            client.get_consoles()

    error = caught.value
    # Sin excepción encadenada: la original de httpx lleva la URL.
    assert error.__cause__ is None
    assert error.__context__ is None
    assert FAKE_KEY not in full_report(error)
    assert "retroachievements.org" not in str(error)
    assert FAKE_KEY not in caplog.text


@pytest.mark.parametrize("key", [FAKE_KEY, "clave/con+signos= y&raros"])
def test_censura_la_url_que_registra_httpx(caplog, key):
    caplog.set_level(logging.DEBUG)
    api = FakeApi()
    with make_client(api, key=key) as client:
        client.get_consoles()

    # La clave sí llega a la API, y httpx sí registra la petición, pero censurada.
    assert api.requests[0].url.params["y"] == key
    messages = [r.getMessage() for r in caplog.records if r.name == "httpx"]
    assert len(messages) == 1
    assert "API_GetConsoleIDs.php?y=***&g=1" in messages[0]
    assert key not in caplog.text
    assert str(api.requests[0].url.query, "ascii").split("&")[0] not in caplog.text


@pytest.mark.parametrize(
    "logger_name", ["httpcore.connection", "httpcore.http11", "httpcore.http2", "httpcore.proxy"]
)
def test_censura_los_registros_de_httpcore(caplog, logger_name):
    caplog.set_level(logging.DEBUG)
    with make_client(FakeApi()):
        logging.getLogger(logger_name).debug("enviando %s", f"/API/x.php?y={FAKE_KEY}")
        logging.getLogger(logger_name).debug("cabecera %s", FAKE_KEY)

    assert "enviando /API/x.php?y=***" in caplog.text
    assert FAKE_KEY not in caplog.text


def test_censura_el_parametro_y_aunque_venga_codificado_de_otra_forma(caplog):
    caplog.set_level(logging.DEBUG)
    with make_client(FakeApi(), key="clave/rara"):
        # Un servidor podría devolver la URL (por ejemplo en "Location") con otra codificación.
        logging.getLogger("httpcore.http11").debug("Location: /x?g=1&y=clave%2frara")

    assert "Location: /x?g=1&y=***" in caplog.text
    assert "%2frara" not in caplog.text


def test_al_cerrar_se_retira_el_filtro_de_los_registros():
    before = list(logging.getLogger("httpx").filters)
    with make_client(FakeApi()):
        assert len(logging.getLogger("httpx").filters) == len(before) + 1
    assert logging.getLogger("httpx").filters == before


def test_los_avisos_de_reintento_no_llevan_la_clave(caplog):
    caplog.set_level(logging.DEBUG)
    api = FakeApi()
    api.failures["consoles"] = [httpx.ConnectError(f"?y={FAKE_KEY}")]
    with make_client(api) as client:
        client.get_consoles()
    assert "se reintenta" in caplog.text
    assert FAKE_KEY not in caplog.text


# --- Selección de consolas ---


def available() -> list[Console]:
    return [Console(id=item["ID"], name=item["Name"]) for item in CONSOLES]


def test_las_consolas_por_defecto_toman_su_id_de_la_api():
    selected = select_consoles(list(DEFAULT_CONSOLES), available())
    assert [(c.id, c.name) for c in selected] == [
        (107, "NES/Famicom"),
        (103, "SNES/Super Famicom"),
        (105, "Game Boy Advance"),
        (101, "Genesis/Mega Drive"),
    ]


@pytest.mark.parametrize(
    ("selector", "expected"),
    [
        ("SNES", 103),
        ("md", 101),
        ("genesis", 101),
        ("Mega Drive", 101),
        ("game boy advance", 105),
        ("Game Boy", 104),
        ("104", 104),
        ("NES/Famicom", 107),
    ],
)
def test_admite_alias_nombres_e_id(selector, expected):
    assert [c.id for c in select_consoles([selector], available())] == [expected]


@pytest.mark.parametrize(
    "name", ["Mega Drive", "Sega Genesis", "Genesis/Mega Drive"]
)
def test_reconoce_los_nombres_oficiales_de_mega_drive(name):
    assert select_consoles(["megadrive"], [Console(id=1, name=name)])


def test_no_repite_consolas():
    selected = select_consoles(["snes", "103", "SNES/Super Famicom"], available())
    assert [c.id for c in selected] == [103]


@pytest.mark.parametrize("selector", ["n64", "999", "Boy", "", "///"])
def test_una_consola_desconocida_falla_y_lista_las_disponibles(selector):
    with pytest.raises(ConsoleSelectionError, match="105: Game Boy Advance"):
        select_consoles(["snes", selector], available())


def test_una_coincidencia_ambigua_falla():
    consoles = [Console(id=1, name="Mega Drive"), Console(id=2, name="Sega Genesis")]
    with pytest.raises(ConsoleSelectionError, match="varias consolas"):
        select_consoles(["megadrive"], consoles)
