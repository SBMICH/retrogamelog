"""Crea un usuario de pruebas en TU base local: python -m app.dev_user

La contraseña es débil a propósito, así que el comando se niega a funcionar fuera de un equipo de
desarrollo. La API no tiene ninguna excepción para este usuario: solo se inserta en la base, y las
reglas de contraseña del registro siguen valiendo para todos los demás.
"""

import os
import sys
from collections.abc import Mapping

from sqlalchemy import func, or_, select
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models import User

DEV_USERNAME = "user123"
DEV_EMAIL = "user123@example.com"
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
LOOPBACK_ADDRESSES = {"127.0.0.1", "::1"}
# Lista de permitidos: muchos parámetros pueden redirigir la conexión (host, hostaddr, service,
# conninfo...), así que solo se aceptan los que seguro no lo hacen.
ALLOWED_URL_PARAMETERS = {"application_name", "connect_timeout", "sslmode"}
VARIABLES_THAT_REDIRECT = ("PGHOSTADDR", "PGSERVICE")
NOT_LOCAL = "Solo funciona con una base de datos en esta máquina (localhost)."


def refusal_reason(environ: Mapping[str, str]) -> str | None:
    """Por qué no se puede crear el usuario en este entorno, o None si se puede."""
    if environ.get("APP_ENV") != "development":
        return "Solo funciona con APP_ENV=development."
    if "RENDER" in environ:
        return "Este entorno es un servidor de Render: no se crea el usuario de desarrollo."
    if any(environ.get(name) for name in VARIABLES_THAT_REDIRECT):
        return f"Quita las variables {', '.join(VARIABLES_THAT_REDIRECT)} antes de continuar."

    try:
        url = make_url(environ.get("DATABASE_URL", ""))
    except Exception:
        # El error original puede citar la URL, con su contraseña.
        return "DATABASE_URL falta o no es válida."
    if url.host not in LOCAL_HOSTS:
        return NOT_LOCAL
    if set(url.query) - ALLOWED_URL_PARAMETERS:
        allowed = ", ".join(sorted(ALLOWED_URL_PARAMETERS))
        return f"DATABASE_URL solo puede llevar estos parámetros: {allowed}."

    if not environ.get("DEV_USER_PASSWORD"):
        return "Falta DEV_USER_PASSWORD (hay un valor de ejemplo en .env.example)."
    return None


def connected_address(db: Session) -> str:
    """Dirección IP a la que de verdad se conectó el cliente de PostgreSQL."""
    return db.connection().connection.driver_connection.info.hostaddr


def create_dev_user(db: Session, password: str) -> str:
    """Crea el usuario si no existe. Nunca modifica una cuenta existente."""
    existing = db.scalars(
        select(User).where(
            or_(func.lower(User.email) == DEV_EMAIL, func.lower(User.username) == DEV_USERNAME)
        )
    ).all()
    if existing:
        if len(existing) == 1 and (existing[0].email, existing[0].username) == (
            DEV_EMAIL,
            DEV_USERNAME,
        ):
            return f"El usuario {DEV_USERNAME} ya existe: no se cambió nada."
        return (
            f"Ya hay otra cuenta con el nombre {DEV_USERNAME} o el correo {DEV_EMAIL}: "
            "no se cambió nada."
        )

    db.add(User(email=DEV_EMAIL, username=DEV_USERNAME, password_hash=hash_password(password)))
    db.commit()
    return f"Usuario {DEV_USERNAME} creado. Inicia sesión con el correo {DEV_EMAIL}."


def main() -> int:
    reason = refusal_reason(os.environ)
    if reason:
        print(f"No se creó el usuario. {reason}", file=sys.stderr)
        return 2

    # Se importa aquí: crear la conexión exige un DATABASE_URL ya comprobado.
    from app.db.session import SessionLocal

    try:
        with SessionLocal() as db:
            # Segunda barrera, que no depende de cómo esté escrita la URL: antes de escribir se
            # comprueba a dónde se conectó realmente.
            if connected_address(db) not in LOOPBACK_ADDRESSES:
                print(f"No se creó el usuario. {NOT_LOCAL}", file=sys.stderr)
                return 2
            print(create_dev_user(db, os.environ["DEV_USER_PASSWORD"]))
    except SQLAlchemyError as error:
        print(
            f"Falló la base de datos ({type(error).__name__}). "
            "Comprueba que está en marcha y migrada (alembic upgrade head).",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
