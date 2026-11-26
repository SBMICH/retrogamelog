"""Reglas que debe cumplir una contraseña nueva. El inicio de sesión no las aplica.

La longitud (8 a 128) la comprueba el esquema de registro; aquí van las demás reglas.
"""

import unicodedata
from pathlib import Path

# Datos personales más cortos que esto aparecen por casualidad en muchas contraseñas.
MIN_PERSONAL_DATA_LENGTH = 3


def _comparable(text: str) -> str:
    """Iguala formas de escribir lo mismo: "é" compuesta o descompuesta, mayúsculas..."""
    return unicodedata.normalize("NFKC", text).casefold()


# Lista corta de contraseñas comunes que sí cumplirían las otras reglas. No es exhaustiva.
COMMON_PASSWORDS = frozenset(
    _comparable(line.strip())
    for line in (Path(__file__).parent / "common_passwords.txt")
    .read_text(encoding="utf-8")
    .splitlines()
    if line.strip() and not line.startswith("#")
)


def password_problem(password: str, username: str | None, email: str | None) -> str | None:
    """Devuelve la regla incumplida, o None si la contraseña sirve.

    El mensaje nunca incluye la contraseña.
    """
    # isdecimal, no isdigit: un superíndice como "²" no cuenta como número.
    if not any(char.isalpha() for char in password) or not any(
        char.isdecimal() for char in password
    ):
        return "La contraseña debe incluir al menos una letra y un número."

    folded = _comparable(password)
    if folded in COMMON_PASSWORDS:
        return "La contraseña es demasiado común: elige otra."

    local_part = email.split("@")[0] if email else None
    for value, name in ((username, "tu nombre de usuario"), (local_part, "tu correo")):
        if value and len(value) >= MIN_PERSONAL_DATA_LENGTH and _comparable(value) in folded:
            return f"La contraseña no puede contener {name}."
    return None
