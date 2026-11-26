"""El catálogo no incluye hacks ni subconjuntos de logros."""

import pytest
from sqlalchemy import func, select

from app.importers.catalog import is_excluded
from app.importers.cli import main
from app.models import Game
from importer_fakes import (  # noqa: F401  (sin_red es una fixture autouse)
    FAKE_KEY,
    FakeApi,
    FakeTime,
    default_games,
    game,
    sin_red,
)

SNES = 103


@pytest.fixture(autouse=True)
def api_key(monkeypatch):
    monkeypatch.setenv("RETROACHIEVEMENTS_API_KEY", FAKE_KEY)


def run(api: FakeApi, *argv: str) -> int:
    return main(list(argv), transport=api.transport, sleep=FakeTime().sleep)


def api_con(titulos: list[str]) -> FakeApi:
    juegos = default_games()
    juegos[SNES] = [game(500 + i, titulo, SNES) for i, titulo in enumerate(titulos)]
    return FakeApi(games=juegos)


def titulos_guardados(db) -> set[str]:
    db.rollback()
    return set(db.scalars(select(Game.title)))


@pytest.mark.parametrize(
    "titulo",
    [
        "~Hack~ Super Mario World: otra aventura",
        "~hack~ en minúsculas",
        "~Hack~ ~Demo~ Prueba",
        "Super Metroid [Subset - Bonus]",
        "Zelda [subset - Reto]",
    ],
)
def test_hacks_y_subconjuntos_se_excluyen(titulo):
    assert is_excluded(titulo)


@pytest.mark.parametrize(
    "titulo",
    [
        "Super Mario World",
        "~Homebrew~ Juego casero",
        "~Prototype~ Prototipo",
        "~Unlicensed~ Sin licencia",
        "~Demo~ Demostración",
        "Hack and Slash",
        "Subset Quest",
    ],
)
def test_los_demas_juegos_se_conservan(titulo):
    assert not is_excluded(titulo)


def test_la_importacion_no_guarda_los_excluidos_y_dice_cuantos(db, capsys):
    api = api_con(["Juego normal", "~Hack~ Copia", "Juego normal [Subset - Bonus]"])

    assert run(api, "--consolas", "snes") == 0

    assert titulos_guardados(db) == {"Juego normal"}
    assert "Excluidos (hacks y subconjuntos): 2" in capsys.readouterr().out


def test_la_simulacion_muestra_que_excluiria(db, capsys):
    api = api_con(["Juego normal", "~Hack~ Copia"])

    assert run(api, "--consolas", "snes", "--simular") == 0

    salida = capsys.readouterr().out
    assert "Excluido: ~Hack~ Copia" in salida
    assert db.scalar(select(func.count()).select_from(Game)) == 0


def test_una_consola_solo_con_excluidos_no_se_confunde_con_una_vacia(db, capsys):
    api = api_con(["~Hack~ Copia"])

    assert run(api, "--consolas", "snes") == 0

    assert "no devolvió ningún juego" not in capsys.readouterr().out
    assert titulos_guardados(db) == set()


def test_no_borra_un_juego_guardado_que_pasa_a_estar_excluido(db):
    run(api_con(["Juego normal"]), "--consolas", "snes")

    run(api_con(["~Hack~ Juego normal"]), "--consolas", "snes")

    assert titulos_guardados(db) == {"Juego normal"}
