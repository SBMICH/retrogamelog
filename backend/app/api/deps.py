"""Dependencias compartidas por los routers.

Toda ruta bajo /me debe pedir `CurrentUser` y filtrar sus consultas por `user.id`.
"""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.config import AuthSettings
from app.core.security import decode_access_token
from app.db.session import SessionLocal
from app.models import User

# La URL es relativa para que "Authorize" en /docs funcione también detrás de un prefijo.
# auto_error=False: así todos los 401 salen de aquí, con el mismo mensaje.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/auth/login", auto_error=False)


def get_db() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session


def get_app_auth_settings(request: Request) -> AuthSettings:
    """La configuración que create_app() leyó y comprobó al arrancar."""
    return request.app.state.auth_settings


DbSession = Annotated[Session, Depends(get_db)]
AppAuthSettings = Annotated[AuthSettings, Depends(get_app_auth_settings)]


def get_current_user(
    token: Annotated[str | None, Depends(oauth2_scheme)],
    db: DbSession,
    settings: AppAuthSettings,
) -> User:
    user_id = decode_access_token(token, settings.jwt_secret) if token else None
    user = db.get(User, user_id) if user_id is not None else None
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No se pudo validar la autenticación.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
