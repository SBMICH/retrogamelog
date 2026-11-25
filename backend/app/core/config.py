import os
from dataclasses import dataclass

# Orígenes del frontend en desarrollo local (servidor de Vite).
DEFAULT_CORS_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]


@dataclass(frozen=True)
class Settings:
    database_url: str


def get_settings() -> Settings:
    """Lee la configuración de las variables de entorno. No hay valores por defecto con credenciales."""
    try:
        return Settings(database_url=os.environ["DATABASE_URL"])
    except KeyError:
        raise RuntimeError("Falta la variable de entorno DATABASE_URL.") from None


def get_cors_origins() -> list[str]:
    """Orígenes desde los que el navegador puede llamar a la API (CORS).

    Se leen de CORS_ORIGINS, separados por comas. Sin la variable se usan los de desarrollo local.
    Nunca se admite "*": hay que nombrar cada origen.
    """
    raw = os.environ.get("CORS_ORIGINS")
    if raw is None:
        return list(DEFAULT_CORS_ORIGINS)

    origins = [item.strip().rstrip("/") for item in raw.split(",") if item.strip()]
    for origin in origins:
        if origin == "*":
            raise RuntimeError("CORS_ORIGINS no admite '*': indica los orígenes uno por uno.")
        if not origin.startswith(("http://", "https://")):
            raise RuntimeError(
                f"CORS_ORIGINS contiene un origen inválido: {origin!r} (debe empezar por http:// o https://)."
            )
    return origins
