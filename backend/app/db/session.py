from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings

# hide_parameters: los errores y logs de SQL no muestran los valores (emails, hashes de contraseñas).
engine = create_engine(get_settings().database_url, pool_pre_ping=True, hide_parameters=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
