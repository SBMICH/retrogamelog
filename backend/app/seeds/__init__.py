"""Datos iniciales de los catálogos compartidos: modelos de dispositivo y emuladores.

Los datos están en `catalog.json`. Se cargan con `python -m app.seeds`.
"""

from app.seeds.loader import (
    CATALOG_PATH,
    Catalog,
    CatalogError,
    LoadResult,
    load_catalog,
    read_catalog,
)

__all__ = [
    "CATALOG_PATH",
    "Catalog",
    "CatalogError",
    "LoadResult",
    "load_catalog",
    "read_catalog",
]
