"""API de RetroAchievements simulada para los tests del importador. Nada de aquí usa la red."""

import httpx
import pytest


@pytest.fixture(autouse=True)
def sin_red(monkeypatch):
    """Red de seguridad: los módulos que importan esta fixture no pueden salir a la red."""

    def refuse(self, request):
        raise AssertionError("Un test del importador intentó usar la red.")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", refuse)


# Clave inventada: solo sirve para comprobar que nunca aparece en la salida.
FAKE_KEY = "ClaveFalsaDePrueba0123456789abcd"

# ID distintos de los reales a propósito: demuestran que el importador los toma de la respuesta.
CONSOLES = [
    {"ID": 101, "Name": "Genesis/Mega Drive"},
    {"ID": 104, "Name": "Game Boy"},
    {"ID": 105, "Name": "Game Boy Advance"},
    {"ID": 103, "Name": "SNES/Super Famicom"},
    {"ID": 107, "Name": "NES/Famicom"},
]


def game(game_id: int, title: str, console_id: int, icon: str | None = None) -> dict:
    """Un juego con la forma de la respuesta documentada, incluidos campos que no deben usarse."""
    return {
        "Title": title,
        "ID": game_id,
        "ConsoleID": console_id,
        "ConsoleName": "da igual",
        "ImageIcon": icon if icon is not None else f"/Images/{game_id:06d}.png",
        "NumAchievements": 10,
        "NumLeaderboards": 0,
        "Points": 100,
        "DateModified": "2022-11-20 03:44:12",
        "ForumTopicID": 1,
        "Hashes": ["0123456789abcdef0123456789abcdef"],
    }


def default_games() -> dict[int, list[dict]]:
    return {
        107: [game(1, "Juego NES", 107)],
        103: [game(2, "Juego SNES", 103), game(3, "Otro de SNES", 103)],
        105: [game(4, "Juego GBA", 105)],
        101: [game(5, "Juego MD", 101)],
    }


class FakeApi:
    """Transporte simulado. Registra las peticiones y permite programar fallos.

    `failures` asocia "consoles" o un ID de consola con una lista de respuestas que se entregan
    antes de la correcta. Cada elemento es un httpx.Response o una excepción que se lanza.
    """

    def __init__(self, consoles: list | None = None, games: dict | None = None):
        self.consoles = CONSOLES if consoles is None else consoles
        self.games = default_games() if games is None else games
        self.failures: dict[object, list] = {}
        self.requests: list[httpx.Request] = []
        self.transport = httpx.MockTransport(self._handle)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        endpoint = request.url.path.rsplit("/", 1)[-1]
        if endpoint == "API_GetConsoleIDs.php":
            key, body = "consoles", self.consoles
        elif endpoint == "API_GetGameList.php":
            key = int(request.url.params["i"])
            body = self.games.get(key, [])
        else:
            return httpx.Response(404)
        pending = self.failures.get(key)
        if pending:
            outcome = pending.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome
        return httpx.Response(200, json=body)

    def calls(self) -> list[str]:
        """Resumen de las peticiones: "consoles" o el ID de consola pedido."""
        return [request.url.params.get("i", "consoles") for request in self.requests]


class FakeTime:
    """Reloj y espera simulados: los tests no duermen de verdad."""

    def __init__(self):
        self.now = 1000.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds
