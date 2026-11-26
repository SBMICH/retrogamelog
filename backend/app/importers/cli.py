"""Comando de importación del catálogo base: python -m app.importers

Cada consola se guarda en su propia transacción: o entra completa (la consola y todos sus juegos)
o no entra. Las llamadas a la API se hacen fuera de la transacción.
"""

import argparse
import logging
import sys
import time
from collections.abc import Callable

import httpx
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.importers.catalog import CREATE, KEEP, UPDATE, ConsoleSummary, import_console
from app.importers.client import RetroAchievementsClient, RetroAchievementsError
from app.importers.consoles import DEFAULT_CONSOLES, ConsoleSelectionError, select_consoles
from app.importers.settings import get_importer_settings
from app.models import Game, Platform

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_BAD_CONFIGURATION = 2

EXAMPLES_IN_SIMULATION = 5


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.importers",
        description="Importa consolas y juegos desde RetroAchievements.",
        epilog=(
            "Requiere las variables de entorno DATABASE_URL y RETROACHIEVEMENTS_API_KEY."
        ),
    )
    parser.add_argument(
        "--consolas",
        nargs="+",
        default=list(DEFAULT_CONSOLES),
        metavar="CONSOLA",
        help=(
            "alias (nes, snes, gba, megadrive o md), nombre exacto de la API entre comillas o ID. "
            f"Por defecto: {' '.join(DEFAULT_CONSOLES)}."
        ),
    )
    parser.add_argument(
        "--simular",
        action="store_true",
        help="consulta la API y la base y muestra lo que haría, sin escribir nada.",
    )
    return parser


def main(
    argv: list[str] | None = None,
    *,
    transport: httpx.BaseTransport | None = None,
    sleep: Callable[[float], None] = time.sleep,
    session_factory: Callable[[], Session] | None = None,
) -> int:
    """Ejecuta el comando. Los argumentos con nombre permiten sustituir la red y la base en tests."""
    args = build_parser().parse_args(argv)
    _prepare_output()

    try:
        api_key = get_importer_settings().api_key
    except RuntimeError as error:
        return _fail(str(error), EXIT_BAD_CONFIGURATION)

    if session_factory is None:
        try:
            from app.db.session import SessionLocal
        except Exception as error:
            # El mensaje del error puede citar partes de la URL, como la contraseña: solo el tipo.
            return _fail(
                "No se pudo configurar la base de datos: revisa DATABASE_URL "
                f"({type(error).__name__}).",
                EXIT_BAD_CONFIGURATION,
            )
        session_factory = SessionLocal

    # Antes de gastar llamadas a la API se comprueba que la base responde y está migrada.
    try:
        with session_factory() as session:
            session.execute(select(Platform.id).limit(1))
            session.execute(select(Game.id).limit(1))
    except SQLAlchemyError as error:
        return _fail(
            f"No se pudo consultar la base de datos ({type(error).__name__}). "
            "Comprueba que está en marcha y migrada (alembic upgrade head).",
            EXIT_FAILED,
        )

    with RetroAchievementsClient(api_key, transport=transport, sleep=sleep) as client:
        try:
            consoles = select_consoles(args.consolas, client.get_consoles())
        except ConsoleSelectionError as error:
            return _fail(str(error), EXIT_BAD_CONFIGURATION)
        except RetroAchievementsError as error:
            return _fail(f"{error} No se escribió nada.", EXIT_FAILED)

        if args.simular:
            print("SIMULACIÓN: no se escribirá nada en la base de datos.")

        done = []
        for position, console in enumerate(consoles):
            try:
                games = client.get_games(console.id)
                summary = _apply(session_factory, console, games, write=not args.simular)
            except (RetroAchievementsError, SQLAlchemyError) as error:
                pending = [c.name for c in consoles[position + 1 :]]
                return _fail(_failure_report(console.name, error, done, pending, args.simular))
            done.append(console.name)
            _print_summary(summary, args.simular)

    if args.simular:
        print("Simulación terminada: no se escribió nada.")
    else:
        print("Importación terminada.")
    return EXIT_OK


def _apply(session_factory, console, games, *, write: bool) -> ConsoleSummary:
    with session_factory() as session:
        if write:
            # Confirma al salir del bloque; ante cualquier error, deshace todo.
            with session.begin():
                return import_console(session, console, games, write=True)
        # Segunda barrera de la simulación: PostgreSQL rechaza cualquier escritura.
        session.execute(text("SET TRANSACTION READ ONLY"))
        summary = import_console(session, console, games, write=False)
        session.rollback()
        return summary


def _print_summary(summary: ConsoleSummary, simulate: bool) -> None:
    if simulate:
        platform = {CREATE: "se crearía", UPDATE: "se actualizaría", KEEP: "sin cambios"}
        new, updated = "por crear", "por actualizar"
    else:
        platform = {CREATE: "creada", UPDATE: "actualizada", KEEP: "sin cambios"}
        new, updated = "creados", "actualizados"
    print(f"{summary.console.name} (ID {summary.console.id})")
    print(f"  Consola: {platform[summary.platform_action]}")
    print(
        f"  Juegos {new}: {len(summary.new_titles)}, "
        f"{updated}: {len(summary.updated_titles)}, sin cambios: {summary.unchanged}"
    )
    if summary.excluded_titles:
        print(f"  Excluidos (hacks y subconjuntos): {len(summary.excluded_titles)}")
    if not (
        summary.new_titles
        or summary.updated_titles
        or summary.unchanged
        or summary.excluded_titles
    ):
        print("  Aviso: la API no devolvió ningún juego para esta consola.")
    if simulate:
        for label, titles in (
            ("Nuevo", summary.new_titles),
            ("Cambia", summary.updated_titles),
            ("Excluido", summary.excluded_titles),
        ):
            for title in titles[:EXAMPLES_IN_SIMULATION]:
                print(f"    {label}: {title}")
            if len(titles) > EXAMPLES_IN_SIMULATION:
                print(f"    ... y {len(titles) - EXAMPLES_IN_SIMULATION} más")


def _failure_report(
    console_name: str, error: Exception, done: list[str], pending: list[str], simulate: bool
) -> str:
    if isinstance(error, SQLAlchemyError):
        reason = f"error de base de datos ({type(error).__name__})."
    else:
        reason = str(error)
    lines = [f"Falló la consola {console_name}: {reason}"]
    if simulate:
        lines.append("Era una simulación: no se escribió nada.")
    else:
        lines.append(f"De {console_name} no se guardó nada.")
        lines.append(f"Consolas ya guardadas: {', '.join(done) or 'ninguna'}.")
    if pending:
        lines.append(f"Consolas sin procesar: {', '.join(pending)}.")
    return "\n".join(lines)


def _prepare_output() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
    # Hay títulos que la consola de Windows no puede representar al redirigir la salida.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")


def _fail(message: str, code: int = EXIT_FAILED) -> int:
    print(message, file=sys.stderr)
    return code
