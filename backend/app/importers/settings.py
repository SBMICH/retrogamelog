import os
from dataclasses import dataclass, field

API_KEY_VARIABLE = "RETROACHIEVEMENTS_API_KEY"


@dataclass(frozen=True)
class ImporterSettings:
    # repr=False: la clave no debe aparecer si alguien imprime o registra la configuración.
    api_key: str = field(repr=False)


def get_importer_settings() -> ImporterSettings:
    """Lee la clave de la API de RetroAchievements. Solo existe como variable de entorno."""
    api_key = os.environ.get(API_KEY_VARIABLE, "").strip()
    if not api_key:
        raise RuntimeError(f"Falta la variable de entorno {API_KEY_VARIABLE}.")
    return ImporterSettings(api_key=api_key)
