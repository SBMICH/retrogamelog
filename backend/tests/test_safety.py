import pytest

from conftest import es_base_de_pruebas


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+psycopg://u:p@localhost:55432/test",
        "postgresql+psycopg://u:p@localhost:5432/retrogamelog_test",
    ],
)
def test_acepta_bases_de_pruebas(url):
    assert es_base_de_pruebas(url)


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+psycopg://u:p@localhost:5432/retrogamelog",
        "postgresql+psycopg://u:p@localhost:5432/test_data",
        "postgresql+psycopg://u:p@localhost:5432",
    ],
)
def test_rechaza_otras_bases(url):
    assert not es_base_de_pruebas(url)
