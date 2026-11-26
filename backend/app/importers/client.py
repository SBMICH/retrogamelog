"""Cliente de la API web de RetroAchievements (solo lo que necesita el importador del catálogo).

Documentación: https://api-docs.retroachievements.org/ (GetConsoleIDs y GetGameList).

La API recibe la clave en la URL (parámetro "y"), así que ninguna excepción ni registro puede
incluir URLs: los errores se construyen aquí, sin encadenar la excepción original de httpx, y los
registros de httpx y httpcore se censuran mientras el cliente está abierto.

Nunca se pide el parámetro "h" (hashes de ROMs), y de cada juego solo se lee su ID, título,
consola e icono.
"""

import json
import logging
import re
import time
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote, quote_plus

import httpx

logger = logging.getLogger(__name__)

API_BASE_URL = "https://retroachievements.org/API/"
# La documentación de la API web no indica el dominio de las imágenes. Este es el que usa la
# biblioteca oficial rcheevos (src/api/rc_api_common.c, RETROACHIEVEMENTS_IMAGE_HOST).
MEDIA_BASE_URL = "https://media.retroachievements.org"
# Solo se acepta la forma de ruta de icono documentada: así nunca se guarda un enlace arbitrario.
ICON_PATH_PATTERN = re.compile(r"/Images/[A-Za-z0-9_-]+\.png")

# La API limita las peticiones sin publicar cifras: se espera entre llamadas y se insiste poco.
PAUSE_SECONDS = 1.0
MAX_ATTEMPTS = 4
BACKOFF_SECONDS = 2.0
MAX_RETRY_AFTER_SECONDS = 120.0
# La lista de juegos de una consola puede ser muy grande.
TIMEOUT = httpx.Timeout(60.0, connect=10.0)

TEMPORARY_STATUS_CODES = frozenset({408, 429, 500, 502, 503, 504, 520, 521, 522, 523, 524})
TEMPORARY_NETWORK_ERRORS = (
    httpx.TimeoutException,
    httpx.NetworkError,
    httpx.RemoteProtocolError,
)

# Longitudes de las columnas (ver docs/diseno-bd.md).
PLATFORM_NAME_LENGTH = 100
GAME_TITLE_LENGTH = 255

HTTP_LOGGERS = (
    "httpx",
    "httpcore.connection",
    "httpcore.http11",
    "httpcore.http2",
    "httpcore.proxy",
    "httpcore.socks",
)

REDACTED = "***"


class RetroAchievementsError(Exception):
    """Fallo al consultar la API. Su mensaje nunca incluye la URL, la clave ni la respuesta."""


@dataclass(frozen=True)
class Console:
    id: int
    name: str


@dataclass(frozen=True)
class RemoteGame:
    id: int
    title: str
    icon_url: str | None


class _RedactKeyFilter(logging.Filter):
    """Quita la clave de los registros de httpx, que incluyen la URL completa."""

    def __init__(self, api_key: str):
        super().__init__()
        self._secrets = {api_key, quote(api_key, safe=""), quote_plus(api_key)}

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        redacted = re.sub(r"([?&]y=)[^&\s\"')]+", rf"\1{REDACTED}", message)
        for secret in sorted(self._secrets, key=len, reverse=True):
            redacted = redacted.replace(secret, REDACTED)
        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True


class RetroAchievementsClient:
    def __init__(
        self,
        api_key: str,
        *,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._api_key = api_key
        self._sleep = sleep
        self._clock = clock
        self._last_request_at: float | None = None
        # Sin seguir redirecciones (valor por defecto de httpx): la clave no viaja a otra URL.
        self._http = httpx.Client(base_url=API_BASE_URL, transport=transport, timeout=TIMEOUT)
        self._log_filter = _RedactKeyFilter(api_key)
        for name in HTTP_LOGGERS:
            logging.getLogger(name).addFilter(self._log_filter)

    def __enter__(self) -> "RetroAchievementsClient":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()
        for name in HTTP_LOGGERS:
            logging.getLogger(name).removeFilter(self._log_filter)

    def get_consoles(self) -> list[Console]:
        """Consolas de la fuente, con sus ID. g=1 excluye los sistemas que no son de juegos."""
        endpoint = "API_GetConsoleIDs.php"
        data = self._get_list(endpoint, {"g": 1})
        consoles = []
        for item in data:
            console_id, name = _id_and_text(item, "Name", PLATFORM_NAME_LENGTH, endpoint)
            consoles.append(Console(id=console_id, name=name))
        return consoles

    def get_games(self, console_id: int) -> list[RemoteGame]:
        """Todos los juegos de una consola en una sola petición (sin "c" la API no pagina)."""
        endpoint = "API_GetGameList.php"
        data = self._get_list(endpoint, {"i": console_id})
        games: dict[int, RemoteGame] = {}
        without_icon = 0
        for item in data:
            game_id, title = _id_and_text(item, "Title", GAME_TITLE_LENGTH, endpoint)
            if item.get("ConsoleID", console_id) != console_id:
                raise RetroAchievementsError(
                    f"{endpoint}: la API devolvió juegos de una consola distinta de la pedida."
                )
            icon_url = _icon_url(item.get("ImageIcon"))
            if icon_url is None and item.get("ImageIcon"):
                without_icon += 1
            games.setdefault(game_id, RemoteGame(id=game_id, title=title, icon_url=icon_url))
        if without_icon:
            logger.warning(
                "%d juegos traen una ruta de icono con formato inesperado; se omite su icono.",
                without_icon,
            )
        return list(games.values())

    def _get_list(self, endpoint: str, params: dict[str, int]) -> list:
        content = self._request(endpoint, params)
        try:
            data = json.loads(content)
        except ValueError:
            data = None
        # Con un ID de consola inválido la API responde {"success": false} en vez de una lista.
        if not isinstance(data, list):
            raise RetroAchievementsError(
                f"{endpoint}: la respuesta no es una lista JSON como indica la documentación."
            )
        return data

    def _request(self, endpoint: str, params: dict[str, int]) -> bytes:
        """GET con pausa entre llamadas y un número limitado de reintentos ante errores temporales."""
        for attempt in range(1, MAX_ATTEMPTS + 1):
            self._wait_between_requests()
            retry_after: float | None = None
            try:
                response = self._http.get(endpoint, params={"y": self._api_key, **params})
            except TEMPORARY_NETWORK_ERRORS as error:
                reason, temporary = f"error de red ({type(error).__name__})", True
            except Exception as error:
                # El texto de la excepción puede incluir la URL: solo se informa su tipo.
                reason, temporary = f"error al hacer la petición ({type(error).__name__})", False
            else:
                if response.status_code == 200:
                    return response.content
                reason = f"HTTP {response.status_code}"
                temporary = response.status_code in TEMPORARY_STATUS_CODES
                retry_after = _retry_after_seconds(response.headers.get("Retry-After"))
                if response.status_code in (401, 403):
                    reason += ": revisa la clave de la API"
            finally:
                self._last_request_at = self._clock()

            # Los errores se lanzan fuera del "except" para que no arrastren la excepción original.
            if not temporary:
                raise RetroAchievementsError(f"{endpoint}: {reason}.")
            if attempt == MAX_ATTEMPTS:
                break
            if retry_after is not None and retry_after > MAX_RETRY_AFTER_SECONDS:
                raise RetroAchievementsError(
                    f"{endpoint}: {reason}. La API pide esperar {retry_after:.0f} segundos; "
                    "vuelve a intentarlo más tarde."
                )
            delay = max(BACKOFF_SECONDS * 2 ** (attempt - 1), retry_after or 0.0)
            logger.warning(
                "%s: %s. Intento %d de %d; se reintenta en %.0f segundos.",
                endpoint,
                reason,
                attempt,
                MAX_ATTEMPTS,
                delay,
            )
            self._sleep(delay)

        raise RetroAchievementsError(f"{endpoint}: {reason}, tras {MAX_ATTEMPTS} intentos.")

    def _wait_between_requests(self) -> None:
        if self._last_request_at is None:
            return
        remaining = PAUSE_SECONDS - (self._clock() - self._last_request_at)
        if remaining > 0:
            self._sleep(remaining)


def _retry_after_seconds(value: str | None) -> float | None:
    """Interpreta la cabecera Retry-After (segundos o fecha HTTP)."""
    if value is None:
        return None
    value = value.strip()
    if re.fullmatch(r"[0-9]+", value):
        return float(value)
    try:
        when = parsedate_to_datetime(value)
        return max(0.0, (when - datetime.now(timezone.utc)).total_seconds())
    except (TypeError, ValueError):
        return None


def _id_and_text(item: object, text_field: str, max_length: int, endpoint: str) -> tuple[int, str]:
    """Valida el ID y el campo de texto obligatorios de un elemento de la respuesta."""
    if isinstance(item, dict):
        item_id = item.get("ID")
        text = item.get(text_field)
        if type(item_id) is int and item_id > 0 and isinstance(text, str):
            # PostgreSQL no admite el carácter nulo ni sustitutos sueltos.
            clean = "".join(
                " " if unicodedata.category(char) in ("Cc", "Cs") else char for char in text
            ).strip()
            if clean:
                if len(clean) > max_length:
                    logger.warning(
                        "El texto del ID %d supera %d caracteres y se recorta.", item_id, max_length
                    )
                    clean = clean[:max_length].rstrip()
                return item_id, clean
    raise RetroAchievementsError(
        f"{endpoint}: la respuesta tiene un elemento sin un ID o un {text_field} válidos."
    )


def _icon_url(path: object) -> str | None:
    if isinstance(path, str) and ICON_PATH_PATTERN.fullmatch(path):
        url = MEDIA_BASE_URL + path
        if len(url) <= 500:
            return url
    return None
