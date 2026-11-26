from alembic import command
from sqlalchemy import inspect

from app.db.base import Base
from app.db.session import engine
from conftest import alembic_config


def test_migracion_se_aplica_y_se_revierte(schema):
    command.downgrade(alembic_config(), "base")
    assert set(inspect(engine).get_table_names()) <= {"alembic_version"}

    command.upgrade(alembic_config(), "head")
    assert set(Base.metadata.tables) <= set(inspect(engine).get_table_names())
    assert len(Base.metadata.tables) == 12
