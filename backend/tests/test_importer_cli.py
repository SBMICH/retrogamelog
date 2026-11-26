"""Importación de extremo a extremo: API simulada y PostgreSQL real."""

import logging
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import sessionmaker

from app.db.session import engine
from app.importers.cli import main
from app.models import Game, GameStatus, Platform, User, UserGame
from importer_fakes import (  # noqa: F401  (sin_red es una fixture autouse)
    CONSOLES,
    FAKE_KEY,
    FakeApi,
    FakeTime,
    default_games,
    game,
    sin_red,
)

BACKEND = Path(__file__).resolve().parent.parent
ICON = "https://media.retroachievements.org/Images/{:06d}.png"


@pytest.fixture(autouse=True)
def api_key(monkeypatch):
    monkeypatch.setenv("RETROACHIEVEMENTS_API_KEY", FAKE_KEY)


def run(api: FakeApi, *argv: str, **kwargs) -> int:
    return main(list(argv), transport=api.transport, sleep=FakeTime().sleep, **kwargs)


def snapshot(db) -> dict:
    """Contenido completo del catálogo, para comprobar que algo no cambió."""
    db.rollback()
    return {
        table: [tuple(row) for row in db.execute(text(f"SELECT * FROM {table} ORDER BY id"))]
        for table in ("platforms", "games")
    }


def count(db, model) -> int:
    db.rollback()
    return db.scalar(select(func.count()).select_from(model))


def find_game(db, external_id: int) -> Game | None:
    db.rollback()
    db.expire_all()
    return db.scalar(select(Game).where(Game.external_id == str(external_id)))


def find_platform(db, external_id: int) -> Platform | None:
    db.rollback()
    db.expire_all()
    return db.scalar(select(Platform).where(Platform.external_id == str(external_id)))


# --- Primera importación ---


def test_importa_las_consolas_por_defecto(db, capsys):
    api = FakeApi()

    assert run(api) == 0

    # Una llamada por la lista de consolas y una por cada consola: ni una más.
    assert api.calls() == ["consoles", "107", "103", "105", "101"]
    assert all("h" not in request.url.params for request in api.requests)
    assert count(db, Platform) == 4
    assert count(db, Game) == 5

    platform = find_platform(db, 103)
    assert (platform.name, platform.source) == ("SNES/Super Famicom", "retroachievements")

    saved = find_game(db, 2)
    assert saved.title == "Juego SNES"
    assert saved.source == "retroachievements"
    assert saved.platform_id == find_platform(db, 103).id
    saved = find_game(db, 2)
    assert saved.icon_url == ICON.format(2)
    assert saved.details_fetched_at is None
    assert (saved.cover_url, saved.release_year, saved.developer) == (None, None, None)

    # Nada de lo guardado contiene los hashes que venían en la respuesta simulada.
    assert "0123456789abcdef" not in repr(snapshot(db))

    out = capsys.readouterr().out
    assert "Juegos creados: 2, actualizados: 0, sin cambios: 0" in out
    assert "Importación terminada." in out


def test_importa_solo_las_consolas_indicadas(db):
    api = FakeApi()
    assert run(api, "--consolas", "gba", "103") == 0
    assert api.calls() == ["consoles", "105", "103"]
    assert count(db, Platform) == 2
    assert count(db, Game) == 3


def test_una_consola_sin_juegos_se_avisa(db, capsys):
    api = FakeApi()
    assert run(api, "--consolas", "104") == 0
    assert "no devolvió ningún juego" in capsys.readouterr().out
    assert count(db, Platform) == 1


# --- Idempotencia ---


def test_repetir_la_importacion_no_duplica_ni_cambia_nada(db, capsys):
    assert run(FakeApi()) == 0
    before = snapshot(db)
    capsys.readouterr()

    assert run(FakeApi()) == 0

    assert snapshot(db) == before
    out = capsys.readouterr().out
    assert "Juegos creados: 0, actualizados: 0, sin cambios: 2" in out
    assert "Consola: sin cambios" in out


def test_actualiza_lo_que_cambio_sin_borrar_datos(db, capsys):
    assert run(FakeApi()) == 0
    capsys.readouterr()

    # Datos que no vienen de la lista de juegos: añadidos a mano o al pedir los detalles.
    fetched = datetime(2026, 1, 2, tzinfo=timezone.utc)
    platform = find_platform(db, 103)
    platform.short_name = "SNES"
    platform.manufacturer = "Nintendo"
    db.commit()
    saved = find_game(db, 2)
    saved.release_year = 1994
    saved.developer = "Un estudio"
    saved.cover_url = "https://example.com/caratula.png"
    saved.details_fetched_at = fetched
    db.commit()
    registered_id = find_game(db, 3).id
    user = User(email="ana@mail.com", username="ana", password_hash="x")
    db.add(user)
    db.flush()
    db.add(UserGame(user_id=user.id, game_id=registered_id, status=GameStatus.backlog))
    db.commit()
    # Un juego puesto a mano, sin fuente.
    db.add(Game(platform_id=find_platform(db, 103).id, title="Manual"))
    db.commit()
    created_at = find_game(db, 2).created_at
    original_id = find_game(db, 2).id

    consoles = [dict(c) for c in CONSOLES]
    consoles[3]["Name"] = "Super Nintendo Entertainment System"
    games = default_games()
    # El 2 cambia título e icono, el 3 desaparece de la fuente y llega el 6.
    games[103] = [
        game(2, "Juego SNES (corregido)", 103, "/Images/999999.png"),
        game(6, "Recién llegado", 103),
    ]
    assert run(FakeApi(consoles=consoles, games=games), "--consolas", "snes") == 0

    out = capsys.readouterr().out
    assert "Consola: actualizada" in out
    assert "Juegos creados: 1, actualizados: 1, sin cambios: 0" in out
    assert count(db, Platform) == 4
    assert count(db, Game) == 7
    assert count(db, UserGame) == 1

    platform = find_platform(db, 103)
    assert platform.name == "Super Nintendo Entertainment System"
    assert (platform.short_name, platform.manufacturer) == ("SNES", "Nintendo")

    saved = find_game(db, 2)
    assert saved.id == original_id
    assert saved.title == "Juego SNES (corregido)"
    assert saved.icon_url == ICON.format(999999)
    assert saved.release_year == 1994
    assert saved.developer == "Un estudio"
    assert saved.cover_url == "https://example.com/caratula.png"
    assert saved.details_fetched_at == fetched
    assert saved.created_at == created_at
    assert find_game(db, 3).title == "Otro de SNES"
    assert db.scalar(select(Game).where(Game.title == "Manual")).source is None


@pytest.mark.parametrize("icon", ["", "/formato/raro.gif"])
def test_un_icono_ausente_no_borra_el_guardado(db, icon):
    assert run(FakeApi(), "--consolas", "nes") == 0

    games = {107: [game(1, "Juego NES", 107, icon)]}
    assert run(FakeApi(games=games), "--consolas", "nes") == 0

    assert find_game(db, 1).icon_url == ICON.format(1)


def test_un_juego_que_cambia_de_consola_se_actualiza(db):
    assert run(FakeApi(), "--consolas", "nes", "snes") == 0

    games = {103: [game(1, "Juego NES", 103)]}
    assert run(FakeApi(games=games), "--consolas", "snes") == 0

    assert find_game(db, 1).platform_id == find_platform(db, 103).id
    assert count(db, Game) == 3


def test_no_confunde_juegos_de_otra_fuente_con_el_mismo_id(db):
    other = Platform(name="Otra", source="otra-fuente", external_id="103")
    db.add(other)
    db.flush()
    db.add(Game(platform_id=other.id, title="Ajeno", source="otra-fuente", external_id="2"))
    db.commit()

    assert run(FakeApi(), "--consolas", "snes") == 0

    assert count(db, Platform) == 2
    assert count(db, Game) == 3
    ajeno = db.scalar(select(Game).where(Game.source == "otra-fuente"))
    assert (ajeno.title, ajeno.platform_id) == ("Ajeno", other.id)


def test_busca_los_juegos_existentes_por_lotes(db, monkeypatch):
    monkeypatch.setattr("app.importers.catalog.LOOKUP_BATCH", 2)
    games = {103: [game(i, f"Juego {i}", 103) for i in range(1, 8)]}

    assert run(FakeApi(games=games), "--consolas", "snes") == 0
    assert run(FakeApi(games=games), "--consolas", "snes") == 0

    assert count(db, Game) == 7


# --- Simulación ---


def test_la_simulacion_no_escribe_nada(db, capsys):
    api = FakeApi()

    assert run(api, "--simular") == 0

    assert api.calls() == ["consoles", "107", "103", "105", "101"]
    assert count(db, Platform) == 0
    assert count(db, Game) == 0
    out = capsys.readouterr().out
    assert "SIMULACIÓN" in out
    assert "Consola: se crearía" in out
    assert "Juegos por crear: 2, por actualizar: 0, sin cambios: 0" in out
    assert "Nuevo: Juego SNES" in out
    assert "no se escribió nada" in out


def test_la_simulacion_muestra_los_cambios_sin_aplicarlos(db, capsys):
    assert run(FakeApi(), "--consolas", "snes") == 0
    before = snapshot(db)
    capsys.readouterr()

    consoles = [dict(c) for c in CONSOLES]
    consoles[3]["Name"] = "Super Nintendo Entertainment System"
    games = {103: [game(2, "Título nuevo", 103)]}
    games[103] += [game(i, f"Extra {i}", 103) for i in range(10, 18)]
    assert run(FakeApi(consoles=consoles, games=games), "--consolas", "snes", "--simular") == 0

    assert snapshot(db) == before
    out = capsys.readouterr().out
    assert "Consola: se actualizaría" in out
    assert "Juegos por crear: 8, por actualizar: 1, sin cambios: 0" in out
    assert "Cambia: Título nuevo" in out
    # Solo unos pocos ejemplos, no la lista entera.
    assert out.count("Nuevo: ") == 5
    assert "... y 3 más" in out


def test_la_simulacion_usa_una_transaccion_de_solo_lectura(db, monkeypatch):
    """Aunque un error de programación intentara escribir, PostgreSQL lo impediría."""
    from app.importers import cli

    real = cli.import_console

    def buggy(session, console, games, *, write):
        return real(session, console, games, write=True)

    monkeypatch.setattr(cli, "import_console", buggy)

    assert run(FakeApi(), "--simular", "--consolas", "snes") == 1
    assert count(db, Platform) == 0


# --- Fallos a mitad ---


def test_un_fallo_de_la_api_conserva_solo_consolas_completas(db, capsys, caplog):
    caplog.set_level(logging.DEBUG)
    api = FakeApi()
    api.failures[103] = [httpx.Response(503)] * 4

    assert run(api) == 1

    # No sigue con las demás consolas tras fallar una.
    assert api.calls() == ["consoles", "107", "103", "103", "103", "103"]
    assert find_platform(db, 107) is not None
    assert find_game(db, 1) is not None
    assert find_platform(db, 103) is None
    assert count(db, Platform) == 1
    assert count(db, Game) == 1

    captured = capsys.readouterr()
    assert "Falló la consola SNES/Super Famicom" in captured.err
    assert "Consolas ya guardadas: NES/Famicom." in captured.err
    assert "Consolas sin procesar: Game Boy Advance, Genesis/Mega Drive." in captured.err
    assert "Importación terminada" not in captured.out
    assert FAKE_KEY not in captured.out + captured.err + caplog.text


@pytest.fixture
def exploding_title(db):
    """PostgreSQL rechaza el juego "Explota": un fallo real con la transacción ya empezada."""
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE FUNCTION rgl_test_explota() RETURNS trigger LANGUAGE plpgsql AS $$ "
                "BEGIN IF NEW.title = 'Explota' THEN RAISE EXCEPTION 'fallo provocado'; END IF; "
                "RETURN NEW; END $$"
            )
        )
        conn.execute(
            text(
                "CREATE TRIGGER rgl_test_explota BEFORE INSERT OR UPDATE ON games "
                "FOR EACH ROW EXECUTE FUNCTION rgl_test_explota()"
            )
        )
    yield "Explota"
    # La sesión del test debe soltar sus bloqueos o el DROP TRIGGER esperaría para siempre.
    db.rollback()
    with engine.begin() as conn:
        conn.execute(text("DROP TRIGGER rgl_test_explota ON games"))
        conn.execute(text("DROP FUNCTION rgl_test_explota()"))


def test_un_fallo_al_escribir_deshace_la_consola_entera(db, capsys, exploding_title):
    games = default_games()
    games[103] = [game(2, "Juego SNES", 103), game(3, exploding_title, 103)]

    assert run(FakeApi(games=games)) == 1

    assert find_platform(db, 103) is None
    assert find_game(db, 2) is None
    assert count(db, Platform) == 1
    assert count(db, Game) == 1
    assert "error de base de datos" in capsys.readouterr().err


def test_un_fallo_al_actualizar_deja_la_consola_como_estaba(db, exploding_title):
    assert run(FakeApi(), "--consolas", "snes") == 0
    before = snapshot(db)

    consoles = [dict(c) for c in CONSOLES]
    consoles[3]["Name"] = "Nombre nuevo"
    games = {
        103: [game(2, "Cambiado", 103), game(3, exploding_title, 103), game(9, "Nuevo", 103)]
    }
    # Por ID: con el nombre nuevo, el alias "snes" ya no la identificaría.
    assert run(FakeApi(consoles=consoles, games=games), "--consolas", "103") == 1

    assert snapshot(db) == before


def test_una_respuesta_invalida_a_mitad_no_guarda_esa_consola(db):
    games = default_games()
    games[103] = [game(2, "Bueno", 103), {"ID": 3}]

    assert run(FakeApi(games=games)) == 1

    assert find_platform(db, 103) is None
    assert find_game(db, 2) is None
    assert count(db, Game) == 1


def test_si_falla_la_lista_de_consolas_no_se_escribe(db, capsys):
    api = FakeApi()
    api.failures["consoles"] = [httpx.Response(401)]

    assert run(api) == 1

    assert api.calls() == ["consoles"]
    assert count(db, Platform) == 0
    err = capsys.readouterr().err
    assert "revisa la clave" in err
    assert FAKE_KEY not in err


# --- Configuración ---


def test_sin_clave_no_llama_a_la_api(db, monkeypatch, capsys):
    monkeypatch.delenv("RETROACHIEVEMENTS_API_KEY")
    api = FakeApi()

    assert run(api) == 2

    assert api.requests == []
    assert "RETROACHIEVEMENTS_API_KEY" in capsys.readouterr().err


def test_una_consola_desconocida_no_importa_nada(db, capsys):
    api = FakeApi()

    assert run(api, "--consolas", "snes", "dreamcast") == 2

    assert api.calls() == ["consoles"]
    assert count(db, Platform) == 0
    assert "'dreamcast' no está" in capsys.readouterr().err


def test_si_la_base_no_responde_no_llama_a_la_api(capsys):
    unreachable = create_engine(
        "postgresql+psycopg://usuario:contrasena-secreta@127.0.0.1:1/test",
        connect_args={"connect_timeout": 2},
    )
    api = FakeApi()

    assert run(api, session_factory=sessionmaker(bind=unreachable)) == 1

    assert api.requests == []
    err = capsys.readouterr().err
    assert "No se pudo consultar la base de datos" in err
    assert "contrasena-secreta" not in err


# --- Comando real (python -m), en un proceso aparte ---


def run_module(*args: str, **env: str) -> subprocess.CompletedProcess:
    environment = {**os.environ, "PYTHONIOENCODING": "utf-8", **env}
    # Si algún fallo dejara pasar una petición real, iría a un proxy inexistente.
    environment.update(HTTPS_PROXY="http://127.0.0.1:9", NO_PROXY="")
    return subprocess.run(
        [sys.executable, "-m", "app.importers", *args],
        cwd=BACKEND,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )


def test_el_comando_existe_y_explica_sus_opciones():
    result = run_module("--help")
    assert result.returncode == 0
    assert "--consolas" in result.stdout
    assert "--simular" in result.stdout


def test_el_comando_sin_clave_termina_con_codigo_2():
    result = run_module(RETROACHIEVEMENTS_API_KEY="")
    assert result.returncode == 2
    assert "RETROACHIEVEMENTS_API_KEY" in result.stderr


@pytest.mark.parametrize(
    "url",
    [
        "",
        "esto-no-es-una-url:contrasena-secreta",
        "postgresql+nada://u:secreta@h/test",
        # Sin "@": SQLAlchemy toma la contraseña por el puerto y la cita en su error.
        "postgresql+psycopg://usuario:secreta",
    ],
)
def test_el_comando_con_database_url_invalida_no_la_muestra(url):
    result = run_module(DATABASE_URL=url, RETROACHIEVEMENTS_API_KEY=FAKE_KEY)

    assert result.returncode == 2
    output = result.stdout + result.stderr
    assert "revisa DATABASE_URL" in output
    assert "secreta" not in output
    assert FAKE_KEY not in output
