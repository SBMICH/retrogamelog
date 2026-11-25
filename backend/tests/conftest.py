import os

# Base de datos desechable de pruebas (ver backend/README.md). Se puede sobrescribir con DATABASE_URL.
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://test:test@localhost:55432/test")

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.db.base import Base  # noqa: E402
from app.db.session import engine  # noqa: E402


def es_base_de_pruebas(url: str) -> bool:
    """Los tests borran todas las tablas: solo se permiten bases cuyo nombre termina en "test"."""
    return (make_url(url).database or "").endswith("test")


def pytest_sessionstart(session):
    # Se ejecuta antes de cualquier fixture, así que no se toca la base si la URL no es de pruebas.
    url = os.environ["DATABASE_URL"]
    if not es_base_de_pruebas(url):
        pytest.exit(
            "DATABASE_URL no apunta a una base de pruebas (el nombre debe terminar en 'test'). "
            "Los tests borran todas las tablas; no se ejecutó nada.",
            returncode=2,
        )


def alembic_config() -> Config:
    return Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))


@pytest.fixture(scope="session", autouse=True)
def schema():
    """Crea el esquema con las migraciones (así también se prueba la migración)."""
    command.downgrade(alembic_config(), "base")
    command.upgrade(alembic_config(), "head")
    yield
    command.downgrade(alembic_config(), "base")


@pytest.fixture
def db(schema):
    with Session(engine) as session:
        yield session
        session.rollback()
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
