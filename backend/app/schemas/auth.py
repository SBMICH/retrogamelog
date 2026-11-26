from typing import Annotated, Literal

from email_validator import EmailNotValidError, validate_email
from pydantic import AfterValidator, BaseModel, Field, TypeAdapter

# Límite de una dirección de correo (RFC 5321); la columna admite 255.
MAX_EMAIL_LENGTH = 254
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128


def _normalizar_email(valor: str) -> str:
    # Los mensajes de error no repiten la entrada: alguien puede escribir la contraseña en este campo.
    # email-validator limita la dirección a 254 bytes, así que cabe en la columna también después de
    # pasarla a minúsculas (lo comprueban los tests).
    try:
        return validate_email(valor.strip(), check_deliverability=False).normalized.lower()
    except EmailNotValidError:
        raise ValueError("El correo electrónico no es válido.") from None


Email = Annotated[
    str,
    Field(max_length=MAX_EMAIL_LENGTH, json_schema_extra={"format": "email"}),
    AfterValidator(_normalizar_email),
]
# El mismo tipo valida y normaliza el email en el registro y en el inicio de sesión.
email_adapter = TypeAdapter(Email)


class UserRegister(BaseModel):
    email: Email
    username: Annotated[str, Field(min_length=3, max_length=30, pattern=r"^[A-Za-z0-9_-]+$")]
    password: Annotated[
        str,
        Field(
            min_length=PASSWORD_MIN_LENGTH,
            max_length=PASSWORD_MAX_LENGTH,
            json_schema_extra={"format": "password"},
        ),
    ]


class Token(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
