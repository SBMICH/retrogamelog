from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import validation_error_handler
from app.api.router import api_router
from app.core.config import get_auth_settings, get_cors_origins


def create_app() -> FastAPI:
    # Se comprueba al arrancar: sin un JWT_SECRET válido, la API no se levanta.
    auth_settings = get_auth_settings()

    app = FastAPI(
        title="RetroGameLog API",
        description="Diario y catálogo de videojuegos retro.",
        version="0.1.0",
    )
    app.state.auth_settings = auth_settings
    app.add_exception_handler(RequestValidationError, validation_error_handler)

    # La autenticación irá por token en la cabecera Authorization, no por cookies,
    # así que no se permiten credenciales entre orígenes.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_cors_origins(),
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.get("/health", tags=["sistema"])
    def health() -> dict[str, str]:
        """Indica que la API está viva. Lo usará Render para comprobar el servicio."""
        return {"status": "ok"}

    app.include_router(api_router)

    return app


app = create_app()
