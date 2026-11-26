from fastapi import APIRouter

from app.api.deps import CurrentUser
from app.models import User
from app.schemas.user import UserOut

# Las rutas futuras bajo /me van aquí o en routers incluidos con este mismo prefijo.
router = APIRouter(
    prefix="/me",
    tags=["cuenta"],
    responses={401: {"description": "Falta el token o no es válido"}},
)


@router.get("", response_model=UserOut)
def read_me(user: CurrentUser) -> User:
    return user
