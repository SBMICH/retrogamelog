"""Escritura del catálogo importado en las tablas platforms y games."""

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.importers.client import Console, RemoteGame
from app.models import Game, Platform

SOURCE = "retroachievements"
# PostgreSQL limita los parámetros por consulta, así que las búsquedas se hacen por lotes.
LOOKUP_BATCH = 5000

CREATE = "crear"
UPDATE = "actualizar"
KEEP = "sin cambios"

# Marcas que RetroAchievements pone en el título: los hacks llevan "~Hack~" delante y los
# subconjuntos de logros "[Subset - Nombre]" detrás. Ver su guía:
# https://docs.retroachievements.org/guidelines/content/game-info-and-hub-guidelines.html
EXCLUDED_TITLE_MARKS = ("~hack~", "[subset - ")


@dataclass
class ConsoleSummary:
    console: Console
    platform_action: str = KEEP
    new_titles: list[str] = field(default_factory=list)
    updated_titles: list[str] = field(default_factory=list)
    unchanged: int = 0
    excluded_titles: list[str] = field(default_factory=list)


def is_excluded(title: str) -> bool:
    """Hacks y subconjuntos no entran en el catálogo. Homebrew, prototipos y sin licencia sí."""
    lowered = title.lower()
    return any(mark in lowered for mark in EXCLUDED_TITLE_MARKS)


def import_console(
    session: Session, console: Console, games: list[RemoteGame], *, write: bool
) -> ConsoleSummary:
    """Compara una consola y sus juegos con la base y, si write es True, guarda las diferencias.

    No hace commit: quien llama decide la transacción. Solo toca los datos que vienen de la fuente
    (nombre de la consola; título, consola e icono del juego), nunca borra filas ni vacía un valor.
    Los hacks y subconjuntos se omiten (ver is_excluded). Con write=False no modifica ningún objeto.
    """
    summary = ConsoleSummary(console)
    summary.excluded_titles = [game.title for game in games if is_excluded(game.title)]
    games = [game for game in games if not is_excluded(game.title)]

    platform = session.scalar(
        select(Platform).where(
            Platform.source == SOURCE, Platform.external_id == str(console.id)
        )
    )
    if platform is None:
        summary.platform_action = CREATE
        if write:
            platform = Platform(name=console.name, source=SOURCE, external_id=str(console.id))
            session.add(platform)
            session.flush()
    elif platform.name != console.name:
        summary.platform_action = UPDATE
        if write:
            platform.name = console.name

    # None solo en una simulación de una consola que todavía no existe.
    platform_id = platform.id if platform is not None else None
    existing = _existing_games(session, [str(game.id) for game in games])

    for remote in games:
        current = existing.get(str(remote.id))
        if current is None:
            summary.new_titles.append(remote.title)
            if write:
                session.add(
                    Game(
                        platform_id=platform_id,
                        title=remote.title,
                        icon_url=remote.icon_url,
                        source=SOURCE,
                        external_id=str(remote.id),
                    )
                )
            continue

        changes: dict[str, object] = {}
        if current.title != remote.title:
            changes["title"] = remote.title
        if current.platform_id != platform_id:
            changes["platform_id"] = platform_id
        if remote.icon_url is not None and current.icon_url != remote.icon_url:
            changes["icon_url"] = remote.icon_url

        if not changes:
            summary.unchanged += 1
            continue
        summary.updated_titles.append(remote.title)
        if write:
            for column, value in changes.items():
                setattr(current, column, value)

    return summary


def _existing_games(session: Session, external_ids: list[str]) -> dict[str, Game]:
    found: dict[str, Game] = {}
    for start in range(0, len(external_ids), LOOKUP_BATCH):
        batch = external_ids[start : start + LOOKUP_BATCH]
        query = select(Game).where(Game.source == SOURCE, Game.external_id.in_(batch))
        found.update({game.external_id: game for game in session.scalars(query)})
    return found
