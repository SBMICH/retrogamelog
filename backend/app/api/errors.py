from fastapi import Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Respuesta 422 sin la entrada recibida.

    Por defecto FastAPI devuelve en "input" (y a veces en "ctx") lo que envió el cliente, que puede
    incluir contraseñas. Solo se devuelven el tipo de error, el campo y el mensaje.
    """
    errors = [{key: error[key] for key in ("type", "loc", "msg")} for error in exc.errors()]
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={"detail": jsonable_encoder(errors)},
    )
