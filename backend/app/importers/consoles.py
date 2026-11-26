"""Elección de las consolas a importar.

Aquí no hay ID de consola: se toman de la lista que devuelve la API (GetConsoleIDs) buscando por
nombre.
"""

import re

from app.importers.client import Console

# Alias admitidos en la línea de comandos y los nombres con que la fuente llama a cada consola,
# tomados de RetroAchievements: RAWeb (config/systems.php), rcheevos (consoleinfo.c) y el ejemplo
# de la documentación de GetConsoleIDs.
ALIASES: dict[str, tuple[str, ...]] = {
    "nes": ("NES/Famicom", "Nintendo Entertainment System"),
    "snes": ("SNES/Super Famicom", "Super Nintendo Entertainment System"),
    "gba": ("Game Boy Advance", "GameBoy Advance"),
    "megadrive": ("Genesis/Mega Drive", "Mega Drive", "Sega Genesis"),
}
# Otras formas de escribir los mismos alias.
SYNONYMS = {"md": "megadrive", "genesis": "megadrive"}

DEFAULT_CONSOLES = ("nes", "snes", "gba", "megadrive")


class ConsoleSelectionError(Exception):
    """Alguna de las consolas pedidas no se puede identificar sin dudas."""


def _normalize(text: str) -> str:
    return re.sub(r"[\W_]+", "", text.casefold())


def _matches(selector: str, available: list[Console]) -> list[Console]:
    selector = selector.strip()
    if re.fullmatch(r"[0-9]+", selector):
        return [console for console in available if console.id == int(selector)]
    key = _normalize(selector)
    names = ALIASES.get(SYNONYMS.get(key, key), (selector,))
    wanted = {_normalize(name) for name in names} - {""}
    return [console for console in available if _normalize(console.name) in wanted]


def select_consoles(selectors: list[str], available: list[Console]) -> list[Console]:
    """Traduce alias, nombres o ID a consolas de la API, sin repetidas y en el orden pedido.

    Si alguna no se identifica, falla entera: no se importa una selección a medias.
    """
    selected: dict[int, Console] = {}
    problems = []
    for selector in selectors:
        found = _matches(selector, available)
        if len(found) == 1:
            selected.setdefault(found[0].id, found[0])
        elif found:
            options = ", ".join(f"{c.id} ({c.name})" for c in found)
            problems.append(f"'{selector}' coincide con varias consolas: {options}. Usa el ID.")
        else:
            problems.append(f"'{selector}' no está en la lista de consolas de la API.")
    if problems:
        listing = "\n".join(
            f"  {console.id}: {console.name}" for console in sorted(available, key=lambda c: c.id)
        )
        raise ConsoleSelectionError("\n".join(problems) + "\nConsolas disponibles:\n" + listing)
    return list(selected.values())
