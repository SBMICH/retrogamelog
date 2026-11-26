from fastapi import APIRouter

from app.api.routes import auth, me

# Todas las rutas de la API cuelgan de /api/v1 (ver docs/endpoints.md).
api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(me.router)
