"""Límite de intentos de inicio de sesión por correo.

Cada intento se anota ANTES de comprobar la contraseña, en una sola sentencia que bloquea la fila.
Si se comprobara primero y se contara después, muchas peticiones simultáneas pasarían todas la
comprobación y podrían probar más contraseñas que el límite. Un inicio correcto borra el contador.

La hora es siempre la de la base de datos.
"""

import math
from datetime import timedelta

from sqlalchemy import and_, case, delete, extract, func, null, or_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import LOGIN_LOCK_MINUTES, MAX_FAILED_LOGINS
from app.models import LoginAttempt

LOCK_TIME = timedelta(minutes=LOGIN_LOCK_MINUTES)


def reserve_login_attempt(db: Session, email: str) -> int | None:
    """Anota un intento para el correo y hace commit.

    Devuelve None si el intento puede seguir, o los segundos que faltan si el correo está bloqueado.
    """
    now = func.now()
    # Se empieza de cero si terminó un bloqueo, o si los fallos sueltos son antiguos.
    expired = or_(
        LoginAttempt.locked_until <= now,
        and_(
            LoginAttempt.locked_until.is_(None),
            LoginAttempt.last_attempt_at <= now - LOCK_TIME,
        ),
    )
    statement = (
        insert(LoginAttempt)
        .values(email=email, failures=1, last_attempt_at=now)
        .on_conflict_do_update(
            index_elements=[LoginAttempt.email],
            set_={
                "failures": case((expired, 1), else_=LoginAttempt.failures + 1),
                "locked_until": case(
                    (expired, null()),
                    # Un bloqueo en curso no se alarga con más intentos.
                    (LoginAttempt.locked_until > now, LoginAttempt.locked_until),
                    (LoginAttempt.failures + 1 >= MAX_FAILED_LOGINS, now + LOCK_TIME),
                    else_=null(),
                ),
                "last_attempt_at": now,
            },
        )
        .returning(LoginAttempt.failures, extract("epoch", LoginAttempt.locked_until - now))
    )
    failures, seconds_left = db.execute(statement).one()
    db.commit()

    if failures <= MAX_FAILED_LOGINS:
        return None
    return max(1, math.ceil(seconds_left))


def clear_login_attempts(db: Session, email: str) -> None:
    db.execute(delete(LoginAttempt).where(LoginAttempt.email == email))
    db.commit()
