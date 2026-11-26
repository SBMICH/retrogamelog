from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import AppAuthSettings, DbSession
from app.core.login_limit import clear_login_attempts, reserve_login_attempt
from app.core.security import (
    DUMMY_PASSWORD_HASH,
    create_access_token,
    hash_password,
    verify_password,
)
from app.models import User
from app.schemas.auth import PASSWORD_MAX_LENGTH, Token, UserRegister, email_adapter
from app.schemas.user import UserOut

router = APIRouter(prefix="/auth", tags=["autenticación"])

# Índices únicos de la tabla users (ver la migración inicial) y el mensaje de cada uno.
DUPLICATE_MESSAGES = {
    "uq_users_email_lower": "El email ya está registrado.",
    "uq_users_username_lower": "El nombre de usuario ya está en uso.",
}


@router.post(
    "/register",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    responses={409: {"description": "El email o el nombre de usuario ya existen"}},
)
def register(data: UserRegister, db: DbSession) -> User:
    user = User(
        email=data.email,
        username=data.username,
        password_hash=hash_password(data.password),
    )
    db.add(user)
    # No se consulta antes si ya existe: dos registros simultáneos pasarían la consulta. Los
    # índices únicos de la base de datos son los que deciden.
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        message = DUPLICATE_MESSAGES.get(error.orig.diag.constraint_name)
        if message is None:
            raise
        raise HTTPException(status.HTTP_409_CONFLICT, detail=message) from None
    return user


def normalize_login_email(value: str) -> str | None:
    """El email tal como se guarda, o None si no puede ser el de ninguna cuenta."""
    try:
        return email_adapter.validate_python(value)
    except ValidationError:
        return None


def authenticate(db: Session, email: str | None, password: str) -> User | None:
    """`email` es el resultado de normalize_login_email."""
    # Una contraseña más larga que el máximo no puede ser de ninguna cuenta. Se descarta antes de
    # mirar el email, así que no revela nada.
    if len(password) > PASSWORD_MAX_LENGTH:
        return None

    user = None
    if email is not None:
        user = db.scalar(select(User).where(func.lower(User.email) == func.lower(email)))

    # Siempre se verifica un hash, exista o no la cuenta, para que el tiempo no la delate.
    password_ok = verify_password(user.password_hash if user else DUMMY_PASSWORD_HASH, password)
    return user if user and password_ok else None


@router.post(
    "/login",
    response_model=Token,
    responses={
        401: {"description": "Email o contraseña incorrectos"},
        429: {"description": "Demasiados intentos fallidos con ese correo"},
    },
)
def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: DbSession,
    settings: AppAuthSettings,
) -> Token:
    """Formulario OAuth2: el campo `username` lleva el **email**."""
    email = normalize_login_email(form.username)
    # Se cuenta igual exista o no la cuenta, para que el bloqueo no la delate.
    if email is not None:
        retry_after = reserve_login_attempt(db, email)
        if retry_after is not None:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Demasiados intentos fallidos. Vuelve a intentarlo más tarde.",
                headers={"Retry-After": str(retry_after)},
            )

    user = authenticate(db, email, form.password)
    if user is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Email o contraseña incorrectos.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    clear_login_attempts(db, email)
    token = create_access_token(user.id, settings.jwt_secret, settings.access_token_expire_minutes)
    return Token(access_token=token)
