"""Lectura del archivo de datos iniciales y carga idempotente en la base.

La carga solo inserta lo que falta: nunca actualiza ni borra filas. Dos nombres que solo se
diferencian en mayúsculas o espacios se consideran el mismo, aunque la restricción única de la
base sí los distinga.
"""

import json
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.catalog import DeviceModel, Emulator

CATALOG_PATH = Path(__file__).with_name("catalog.json")


class CatalogError(ValueError):
    """El archivo de datos no se puede leer o tiene un error."""


@dataclass(frozen=True)
class Catalog:
    device_models: list[tuple[str, str]]  # (marca, nombre)
    emulators: list[str]


@dataclass(frozen=True)
class LoadResult:
    new_device_models: int
    existing_device_models: int
    new_emulators: int
    existing_emulators: int


def comparison_key(value: str) -> str:
    """Clave para comparar nombres sin distinguir mayúsculas ni espacios."""
    return "".join(value.split()).casefold()


def _clean_text(value: object, max_length: int, where: str) -> str:
    """Valida un texto del archivo y le quita los espacios sobrantes."""
    if not isinstance(value, str):
        raise CatalogError(f"{where}: debe ser un texto.")
    text = " ".join(value.split())
    if not text:
        raise CatalogError(f"{where}: no puede estar vacío.")
    if len(text) > max_length:
        raise CatalogError(f"{where}: supera los {max_length} caracteres.")
    return text


def read_catalog(path: Path = CATALOG_PATH) -> Catalog:
    """Lee y valida el archivo de datos. No toca la base."""
    try:
        # utf-8-sig: también acepta el archivo si un editor le agrega BOM.
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except OSError as error:
        raise CatalogError(f"No se pudo leer {path}: {error.strerror}.") from None
    except UnicodeDecodeError:
        raise CatalogError(f"{path} no está en UTF-8.") from None
    except json.JSONDecodeError as error:
        raise CatalogError(
            f"{path} no es JSON válido (línea {error.lineno}, columna {error.colno}): {error.msg}."
        ) from None

    if (
        not isinstance(data, dict)
        or set(data) != {"device_models", "emulators"}
        or not all(isinstance(value, list) for value in data.values())
    ):
        raise CatalogError('El archivo debe tener exactamente las listas "device_models" y "emulators".')

    device_models: list[tuple[str, str]] = []
    seen_models: set[tuple[str, str]] = set()
    for number, entry in enumerate(data["device_models"], start=1):
        where = f"device_models, elemento {number}"
        if not isinstance(entry, dict) or set(entry) != {"brand", "name"}:
            raise CatalogError(f'{where}: debe tener exactamente "brand" y "name".')
        brand = _clean_text(entry["brand"], DeviceModel.brand.type.length, f"{where}, brand")
        name = _clean_text(entry["name"], DeviceModel.name.type.length, f"{where}, name")
        key = (comparison_key(brand), comparison_key(name))
        if key in seen_models:
            raise CatalogError(f"{where}: '{brand} / {name}' está repetido.")
        seen_models.add(key)
        device_models.append((brand, name))

    emulators: list[str] = []
    seen_emulators: set[str] = set()
    for number, entry in enumerate(data["emulators"], start=1):
        where = f"emulators, elemento {number}"
        name = _clean_text(entry, Emulator.name.type.length, where)
        key = comparison_key(name)
        if key in seen_emulators:
            raise CatalogError(f"{where}: '{name}' está repetido.")
        seen_emulators.add(key)
        emulators.append(name)

    return Catalog(device_models=device_models, emulators=emulators)


def load_catalog(session: Session, catalog: Catalog) -> LoadResult:
    """Inserta en la sesión lo que falte del catálogo. El commit es de quien llama."""
    existing_models = {
        (comparison_key(brand), comparison_key(name))
        for brand, name in session.execute(select(DeviceModel.brand, DeviceModel.name))
    }
    new_models = [
        DeviceModel(brand=brand, name=name)
        for brand, name in catalog.device_models
        if (comparison_key(brand), comparison_key(name)) not in existing_models
    ]

    existing_emulators = {comparison_key(name) for name in session.scalars(select(Emulator.name))}
    new_emulators = [
        Emulator(name=name)
        for name in catalog.emulators
        if comparison_key(name) not in existing_emulators
    ]

    session.add_all([*new_models, *new_emulators])
    session.flush()

    return LoadResult(
        new_device_models=len(new_models),
        existing_device_models=len(catalog.device_models) - len(new_models),
        new_emulators=len(new_emulators),
        existing_emulators=len(catalog.emulators) - len(new_emulators),
    )
