from datetime import datetime

from pydantic import BaseModel, ConfigDict


class UserOut(BaseModel):
    """Datos de la propia cuenta. Lista explícita de campos: el hash de la contraseña nunca sale."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    username: str
    is_public: bool
    created_at: datetime
