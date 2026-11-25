from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_cors_origins


def create_app() -> FastAPI:
    app = FastAPI(
        title="RetroGameLog API",
        description="Diario y catálogo de videojuegos retro.",
        version="0.1.0",
    )

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

    return app


app = create_app()
