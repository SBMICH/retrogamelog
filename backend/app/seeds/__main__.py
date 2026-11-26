"""Comando `python -m app.seeds`: carga los datos iniciales en la base de DATABASE_URL."""

import sys

from app.seeds.loader import CatalogError, load_catalog, read_catalog


def main() -> int:
    try:
        # El archivo se valida antes de abrir la base.
        catalog = read_catalog()
        # Se importa aquí porque, sin DATABASE_URL, falla al importarse.
        from app.db.session import SessionLocal
    except (CatalogError, RuntimeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    # Una sola transacción: o se carga todo o no se carga nada.
    with SessionLocal.begin() as session:
        result = load_catalog(session, catalog)

    print(
        f"Modelos de dispositivo: {result.new_device_models} nuevos, "
        f"{result.existing_device_models} ya existían."
    )
    print(f"Emuladores: {result.new_emulators} nuevos, {result.existing_emulators} ya existían.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
