import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str


def get_settings() -> Settings:
    """Lee la configuración de las variables de entorno. No hay valores por defecto con credenciales."""
    try:
        return Settings(database_url=os.environ["DATABASE_URL"])
    except KeyError:
        raise RuntimeError("Falta la variable de entorno DATABASE_URL.") from None
