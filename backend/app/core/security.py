"""Hash de contraseñas (argon2id) y tokens de acceso (JWT)."""

import re
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

# Fijado en el servidor: nunca se toma de la cabecera del token que llega.
JWT_ALGORITHM = "HS256"

# El "sub" es el ID del usuario: un entero positivo que quepa en la columna (int de PostgreSQL).
_SUBJECT_PATTERN = re.compile(r"[1-9][0-9]{0,9}")
_MAX_USER_ID = 2**31 - 1

# Parámetros por defecto de argon2-cffi (argon2id, RFC 9106 de poca memoria).
_hasher = PasswordHasher()

# Hash de una contraseña aleatoria que nadie conoce. El login lo verifica cuando el email no
# existe, para tardar lo mismo que con una contraseña incorrecta y no revelar qué cuentas hay.
DUMMY_PASSWORD_HASH = _hasher.hash(secrets.token_urlsafe(32))


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def create_access_token(user_id: int, secret: str, expires_minutes: int) -> str:
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)
    return jwt.encode({"sub": str(user_id), "exp": expires_at}, secret, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str, secret: str) -> int | None:
    """Devuelve el ID de usuario del token, o None si el token no es válido."""
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=[JWT_ALGORITHM],
            options={"require": ["exp", "sub"]},
        )
    except jwt.InvalidTokenError:
        return None

    subject = payload["sub"]
    if not _SUBJECT_PATTERN.fullmatch(subject):
        return None
    user_id = int(subject)
    return user_id if user_id <= _MAX_USER_ID else None
