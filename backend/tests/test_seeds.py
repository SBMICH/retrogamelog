"""Tests de la carga de datos iniciales (modelos de dispositivo y emuladores)."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.models import DeviceModel, Emulator
from app.seeds import CATALOG_PATH, Catalog, CatalogError, load_catalog, read_catalog
from app.seeds import __main__ as comando

BACKEND_DIR = Path(__file__).resolve().parent.parent

CATALOGO_CORTO = Catalog(
    device_models=[("Retroid", "Retroid Pocket 5"), ("Anbernic", "Anbernic RG35XX H")],
    emulators=["PPSSPP", "RetroArch (Snes9x)"],
)


def modelos(db):
    consulta = select(DeviceModel.id, DeviceModel.brand, DeviceModel.name).order_by(DeviceModel.id)
    return [tuple(fila) for fila in db.execute(consulta)]


def emuladores(db):
    return [tuple(f) for f in db.execute(select(Emulator.id, Emulator.name).order_by(Emulator.id))]


def total(db, modelo):
    return db.scalar(select(func.count()).select_from(modelo))


def escribir(tmp_path, contenido):
    archivo = tmp_path / "catalogo.json"
    texto = contenido if isinstance(contenido, str) else json.dumps(contenido)
    archivo.write_text(texto, encoding="utf-8")
    return archivo


def ejecutar_comando(env):
    return subprocess.run(
        [sys.executable, "-m", "app.seeds"],
        cwd=BACKEND_DIR,
        env={**env, "PYTHONIOENCODING": "utf-8"},
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )


# --- Carga e idempotencia ---


def test_carga_el_catalogo_en_una_base_vacia(db):
    resultado = load_catalog(db, CATALOGO_CORTO)
    db.commit()

    assert [fila[1:] for fila in modelos(db)] == CATALOGO_CORTO.device_models
    assert [fila[1] for fila in emuladores(db)] == CATALOGO_CORTO.emulators
    assert (resultado.new_device_models, resultado.existing_device_models) == (2, 0)
    assert (resultado.new_emulators, resultado.existing_emulators) == (2, 0)


def test_cargar_varias_veces_no_duplica_ni_cambia_filas(db):
    load_catalog(db, CATALOGO_CORTO)
    db.commit()
    antes = modelos(db), emuladores(db)

    for _ in range(2):
        resultado = load_catalog(db, CATALOGO_CORTO)
        db.commit()

    assert (modelos(db), emuladores(db)) == antes
    assert (resultado.new_device_models, resultado.existing_device_models) == (0, 2)
    assert (resultado.new_emulators, resultado.existing_emulators) == (0, 2)


def test_no_borra_las_filas_anadidas_a_mano(db):
    db.add_all([DeviceModel(brand="Casera", name="Consola X"), Emulator(name="Mi emulador")])
    db.commit()
    modelo_manual, emulador_manual = modelos(db)[0], emuladores(db)[0]

    load_catalog(db, CATALOGO_CORTO)
    load_catalog(db, CATALOGO_CORTO)
    db.commit()

    assert modelo_manual in modelos(db)
    assert emulador_manual in emuladores(db)
    assert total(db, DeviceModel) == 3
    assert total(db, Emulator) == 3


@pytest.mark.parametrize(
    ("marca", "nombre", "emulador"),
    [
        ("retroid", "retroid pocket 5", "ppsspp"),
        ("RETROID", "RETROID POCKET 5", "PPSSPP "),
        (" Retroid ", "Retroid   Pocket5", " P P SSPP"),
    ],
)
def test_no_duplica_variantes_de_mayusculas_o_espacios(db, marca, nombre, emulador):
    db.add_all([DeviceModel(brand=marca, name=nombre), Emulator(name=emulador)])
    db.commit()

    resultado = load_catalog(db, CATALOGO_CORTO)
    db.commit()

    assert (resultado.new_device_models, resultado.new_emulators) == (1, 1)
    assert total(db, DeviceModel) == 2
    assert total(db, Emulator) == 2
    # La fila escrita a mano se deja como estaba.
    assert modelos(db)[0][1:] == (marca, nombre)
    assert emuladores(db)[0][1] == emulador


def test_una_entrada_nueva_en_el_archivo_se_anade_en_la_siguiente_carga(db):
    load_catalog(db, CATALOGO_CORTO)
    db.commit()
    ampliado = Catalog(
        device_models=[*CATALOGO_CORTO.device_models, ("AYN", "AYN Thor")],
        emulators=[*CATALOGO_CORTO.emulators, "Dolphin"],
    )

    resultado = load_catalog(db, ampliado)
    db.commit()

    assert (resultado.new_device_models, resultado.new_emulators) == (1, 1)
    assert total(db, DeviceModel) == 3
    assert total(db, Emulator) == 3


def test_la_carga_no_hace_commit(db):
    load_catalog(db, CATALOGO_CORTO)
    db.rollback()

    assert total(db, DeviceModel) == 0
    assert total(db, Emulator) == 0


# --- Comando de línea ---


def test_el_comando_carga_el_archivo_real_y_se_puede_repetir(db):
    catalogo = read_catalog()
    n_modelos, n_emuladores = len(catalogo.device_models), len(catalogo.emulators)

    primera = ejecutar_comando(os.environ)
    assert primera.returncode == 0, primera.stderr
    assert f"Modelos de dispositivo: {n_modelos} nuevos, 0 ya existían." in primera.stdout
    assert f"Emuladores: {n_emuladores} nuevos, 0 ya existían." in primera.stdout
    filas = modelos(db), emuladores(db)
    db.rollback()

    segunda = ejecutar_comando(os.environ)
    assert segunda.returncode == 0, segunda.stderr
    assert f"Modelos de dispositivo: 0 nuevos, {n_modelos} ya existían." in segunda.stdout
    assert f"Emuladores: 0 nuevos, {n_emuladores} ya existían." in segunda.stdout
    assert (modelos(db), emuladores(db)) == filas
    assert total(db, DeviceModel) == n_modelos
    assert total(db, Emulator) == n_emuladores


def test_el_comando_sin_database_url_explica_el_error():
    env = {clave: valor for clave, valor in os.environ.items() if clave != "DATABASE_URL"}

    resultado = ejecutar_comando(env)

    assert resultado.returncode == 1
    assert "Falta la variable de entorno DATABASE_URL." in resultado.stderr
    assert "Traceback" not in resultado.stderr


def test_el_comando_con_un_archivo_erroneo_no_carga_nada(db, monkeypatch, capsys):
    def leer_mal():
        raise CatalogError("archivo roto")

    monkeypatch.setattr(comando, "read_catalog", leer_mal)

    assert comando.main() == 1
    assert "Error: archivo roto" in capsys.readouterr().err
    assert total(db, DeviceModel) == 0
    assert total(db, Emulator) == 0


def test_el_comando_no_deja_cargas_a_medias(db, monkeypatch):
    def cargar_y_fallar(session, catalog):
        load_catalog(session, catalog)
        raise RuntimeError("fallo a mitad de la carga")

    monkeypatch.setattr(comando, "load_catalog", cargar_y_fallar)

    with pytest.raises(RuntimeError, match="a mitad"):
        comando.main()
    assert total(db, DeviceModel) == 0
    assert total(db, Emulator) == 0


# --- Archivo de datos ---


def test_el_archivo_real_es_valido_y_coherente():
    catalogo = read_catalog()
    crudo = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))

    # Escrito sin espacios sobrantes: lo que se lee es exactamente lo que hay en el archivo.
    assert [(m["brand"], m["name"]) for m in crudo["device_models"]] == catalogo.device_models
    assert crudo["emulators"] == catalogo.emulators

    assert len(catalogo.device_models) >= 15
    assert catalogo.emulators
    marcas = {marca for marca, _ in catalogo.device_models}
    assert {"Retroid", "Anbernic"} <= marcas
    # Cada marca se escribe de una sola forma.
    assert len({marca.casefold() for marca in marcas}) == len(marcas)
    # El nombre es el comercial completo, con la marca delante (Steam Deck no la lleva).
    for marca, nombre in catalogo.device_models:
        prefijo = "Steam Deck" if marca == "Valve" else marca
        assert nombre.startswith(f"{prefijo} "), nombre


def test_la_lectura_quita_los_espacios_sobrantes(tmp_path):
    archivo = escribir(
        tmp_path,
        {
            "device_models": [{"brand": " Retroid ", "name": "Retroid   Pocket 5 "}],
            "emulators": ["  RetroArch   (Snes9x) "],
        },
    )

    catalogo = read_catalog(archivo)

    assert catalogo.device_models == [("Retroid", "Retroid Pocket 5")]
    assert catalogo.emulators == ["RetroArch (Snes9x)"]


def test_acepta_el_archivo_guardado_con_bom(tmp_path):
    archivo = tmp_path / "catalogo.json"
    archivo.write_text('{"device_models": [], "emulators": ["MAME"]}', encoding="utf-8-sig")

    assert read_catalog(archivo).emulators == ["MAME"]


def con_modelos(*entradas):
    return {"device_models": list(entradas), "emulators": []}


def con_emuladores(*entradas):
    return {"device_models": [], "emulators": list(entradas)}


@pytest.mark.parametrize(
    ("contenido", "mensaje"),
    [
        ('{"device_models": [', "no es JSON válido"),
        ([], "exactamente las listas"),
        ({"device_models": []}, "exactamente las listas"),
        ({"device_models": [], "emulators": [], "genres": []}, "exactamente las listas"),
        ({"device_models": [], "emulators": "MAME"}, "exactamente las listas"),
        (con_modelos("Retroid Pocket 5"), 'exactamente "brand" y "name"'),
        (con_modelos({"brand": "Retroid"}), 'exactamente "brand" y "name"'),
        (con_modelos({"brand": "AYN", "name": "AYN Thor", "year": 1}), 'exactamente "brand" y "name"'),
        (con_modelos({"brand": "AYN", "name": 3}), "name: debe ser un texto"),
        (con_modelos({"brand": "  ", "name": "AYN Thor"}), "brand: no puede estar vacío"),
        (con_modelos({"brand": "x" * 51, "name": "y"}), "brand: supera los 50"),
        (con_modelos({"brand": "x", "name": "y" * 101}), "name: supera los 100"),
        (con_emuladores(""), "no puede estar vacío"),
        (con_emuladores(None), "debe ser un texto"),
        (con_emuladores("y" * 101), "supera los 100"),
        (
            con_modelos(
                {"brand": "AYN", "name": "AYN Odin 2"},
                {"brand": "ayn", "name": "AYN  Odin2"},
            ),
            "elemento 2: 'ayn / AYN Odin2' está repetido",
        ),
        (con_emuladores("PPSSPP", " ppsspp"), "elemento 2: 'ppsspp' está repetido"),
    ],
)
def test_rechaza_archivos_con_errores(tmp_path, contenido, mensaje):
    with pytest.raises(CatalogError, match=mensaje):
        read_catalog(escribir(tmp_path, contenido))


def test_rechaza_un_archivo_que_no_existe(tmp_path):
    with pytest.raises(CatalogError, match="No se pudo leer"):
        read_catalog(tmp_path / "no-existe.json")


def test_rechaza_un_archivo_que_no_esta_en_utf8(tmp_path):
    archivo = tmp_path / "catalogo.json"
    archivo.write_bytes('{"device_models": [], "emulators": ["ñ"]}'.encode("cp1252"))

    with pytest.raises(CatalogError, match="no está en UTF-8"):
        read_catalog(archivo)
