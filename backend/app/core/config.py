import os
from dataclasses import dataclass, field

# Orígenes del frontend en desarrollo local (servidor de Vite).
DEFAULT_CORS_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]

# HS256 necesita una clave de al menos 256 bits (RFC 7518, sección 3.2).
MIN_JWT_SECRET_LENGTH = 32
DEFAULT_ACCESS_TOKEN_EXPIRE_MINUTES = 60
# Sin token de refresco, un token robado vale hasta que caduca: no más de una semana.
MAX_ACCESS_TOKEN_EXPIRE_MINUTES = 7 * 24 * 60


@dataclass(frozen=True)
class Settings:
    database_url: str


def get_settings() -> Settings:
    """Lee la configuración de las variables de entorno. No hay valores por defecto con credenciales."""
    try:
        return Settings(database_url=os.environ["DATABASE_URL"])
    except KeyError:
        raise RuntimeError("Falta la variable de entorno DATABASE_URL.") from None


@dataclass(frozen=True)
class AuthSettings:
    # repr=False: el secreto no aparece si alguien imprime o registra la configuración.
    jwt_secret: str = field(repr=False)
    access_token_expire_minutes: int


def get_auth_settings() -> AuthSettings:
    """Configuración de los tokens. JWT_SECRET no tiene valor por defecto: sin él, la API no arranca."""
    secret = os.environ.get("JWT_SECRET")
    if secret is None:
        raise RuntimeError("Falta la variable de entorno JWT_SECRET.")
    if len(secret.strip()) < MIN_JWT_SECRET_LENGTH:
        raise RuntimeError(
            f"JWT_SECRET es demasiado corto: necesita al menos {MIN_JWT_SECRET_LENGTH} caracteres."
        )

    raw = os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", str(DEFAULT_ACCESS_TOKEN_EXPIRE_MINUTES))
    try:
        minutes = int(raw)
    except ValueError:
        minutes = 0
    if not 1 <= minutes <= MAX_ACCESS_TOKEN_EXPIRE_MINUTES:
        raise RuntimeError(
            f"ACCESS_TOKEN_EXPIRE_MINUTES debe ser un entero entre 1 y {MAX_ACCESS_TOKEN_EXPIRE_MINUTES}."
        )
    return AuthSettings(jwt_secret=secret, access_token_expire_minutes=minutes)


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
