import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.models import (
    Device,
    DeviceModel,
    Game,
    GameStatus,
    LogEntry,
    LogKind,
    Performance,
    PlaySetup,
    Platform,
    User,
    UserGame,
)


def count(db, model) -> int:
    return db.scalar(select(func.count()).select_from(model))


def make_user(db, email="ana@mail.com", username="ana") -> User:
    user = User(email=email, username=username, password_hash="x")
    db.add(user)
    db.flush()
    return user


def make_platform(db, **kwargs) -> Platform:
    platform = Platform(name="Super Nintendo", **kwargs)
    db.add(platform)
    db.flush()
    return platform


def make_game(db, platform=None, **kwargs) -> Game:
    platform = platform or make_platform(db)
    game = Game(platform_id=platform.id, title="Super Metroid", **kwargs)
    db.add(game)
    db.flush()
    return game


def make_user_game(db, user, game, **kwargs) -> UserGame:
    kwargs.setdefault("status", GameStatus.backlog)
    user_game = UserGame(user_id=user.id, game_id=game.id, **kwargs)
    db.add(user_game)
    db.flush()
    return user_game


def test_user_game_unico_por_usuario_y_juego(db):
    user, game = make_user(db), make_game(db)
    make_user_game(db, user, game)
    with pytest.raises(IntegrityError):
        make_user_game(db, user, game)


def test_games_source_external_id_unico(db):
    platform = make_platform(db)
    make_game(db, platform, source="retroachievements", external_id="1")
    with pytest.raises(IntegrityError):
        make_game(db, platform, source="retroachievements", external_id="1")


def test_platforms_source_external_id_unico(db):
    make_platform(db, source="retroachievements", external_id="3")
    with pytest.raises(IntegrityError):
        make_platform(db, source="retroachievements", external_id="3")


@pytest.mark.parametrize("rating", [0, 11])
def test_rating_fuera_de_rango(db, rating):
    user, game = make_user(db), make_game(db)
    with pytest.raises(IntegrityError):
        make_user_game(db, user, game, rating=rating)


@pytest.mark.parametrize("rating", [1, 10])
def test_rating_en_rango(db, rating):
    user, game = make_user(db), make_game(db)
    assert make_user_game(db, user, game, rating=rating).rating == rating


@pytest.mark.parametrize("priority", [0, 4])
def test_prioridad_fuera_de_rango(db, priority):
    user, game = make_user(db), make_game(db)
    with pytest.raises(IntegrityError):
        make_user_game(db, user, game, priority=priority)


def test_email_unico_sin_distinguir_mayusculas(db):
    make_user(db, email="ana@mail.com", username="ana")
    with pytest.raises(IntegrityError):
        make_user(db, email="ANA@mail.com", username="otra")


def test_username_unico_sin_distinguir_mayusculas(db):
    make_user(db, email="a@mail.com", username="Ana")
    with pytest.raises(IntegrityError):
        make_user(db, email="b@mail.com", username="ANA")


def test_borrar_usuario_borra_todo_lo_suyo(db):
    user, game = make_user(db), make_game(db)
    user_game = make_user_game(db, user, game)
    model = DeviceModel(brand="Retroid", name="Pocket 5")
    db.add(model)
    db.flush()
    device = Device(user_id=user.id, device_model_id=model.id)
    db.add(device)
    db.flush()
    db.add(LogEntry(user_game_id=user_game.id, kind=LogKind.note, entry_date="2026-01-01"))
    db.add(PlaySetup(user_game_id=user_game.id, device_id=device.id, performance=Performance.perfect))
    db.flush()

    db.delete(user)
    db.flush()

    for table in (UserGame, LogEntry, Device, PlaySetup):
        assert count(db, table) == 0
    # El catálogo no se toca.
    assert count(db, Game) == 1
    assert count(db, DeviceModel) == 1


def test_borrar_user_game_borra_historial_y_configuraciones(db):
    user, game = make_user(db), make_game(db)
    user_game = make_user_game(db, user, game)
    model = DeviceModel(brand="Retroid", name="Pocket 5")
    db.add(model)
    db.flush()
    device = Device(user_id=user.id, device_model_id=model.id)
    db.add(device)
    db.flush()
    db.add(LogEntry(user_game_id=user_game.id, kind=LogKind.started, entry_date="2026-01-01"))
    db.add(PlaySetup(user_game_id=user_game.id, device_id=device.id, performance=Performance.playable))
    db.flush()

    db.delete(user_game)
    db.flush()

    assert count(db, LogEntry) == 0
    assert count(db, PlaySetup) == 0
    assert count(db, Device) == 1


def test_no_se_puede_borrar_dispositivo_con_configuraciones(db):
    user, game = make_user(db), make_game(db)
    user_game = make_user_game(db, user, game)
    model = DeviceModel(brand="Retroid", name="Pocket 5")
    db.add(model)
    db.flush()
    device = Device(user_id=user.id, device_model_id=model.id)
    db.add(device)
    db.flush()
    db.add(PlaySetup(user_game_id=user_game.id, device_id=device.id, performance=Performance.issues))
    db.flush()

    # La comprobación se difiere al commit.
    db.delete(device)
    with pytest.raises(IntegrityError):
        db.commit()
