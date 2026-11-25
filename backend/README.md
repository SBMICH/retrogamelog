# Backend

API de RetroGameLog (FastAPI + SQLAlchemy 2 + PostgreSQL). El diseño de la base de datos está en `../docs/diseno-bd.md`.

## Preparación

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

## Configuración

Todo se lee de variables de entorno:

| Variable | Obligatoria | Ejemplo |
|---|---|---|
| `DATABASE_URL` | Sí | `postgresql+psycopg://usuario:clave@localhost:5432/retrogamelog` |
| `CORS_ORIGINS` | No | `https://retrogamelog.example,https://www.retrogamelog.example` |

`CORS_ORIGINS` es la lista (separada por comas) de orígenes del frontend a los que el navegador deja llamar a la API. Si no se define, se usan los de desarrollo local (`http://localhost:5173` y `http://127.0.0.1:5173`). No se admite `*`, y cada origen debe empezar por `http://` o `https://`. En producción hay que definirla con la URL real del frontend.

## Migraciones (Alembic)

```powershell
$env:DATABASE_URL = "postgresql+psycopg://..."
.\.venv\Scripts\alembic.exe upgrade head      # aplicar
.\.venv\Scripts\alembic.exe downgrade base    # revertir todo
.\.venv\Scripts\alembic.exe revision --autogenerate -m "descripción"
```

## Tests

Los tests usan PostgreSQL real y **borran todas las tablas** al terminar, así que nunca apuntes `DATABASE_URL` a una base con datos. Usa un contenedor desechable:

```powershell
docker run -d --name rgl-test-db -p 55432:5432 -e POSTGRES_USER=test -e POSTGRES_PASSWORD=test -e POSTGRES_DB=test postgres:16
.\.venv\Scripts\python.exe -m pytest
docker rm -f rgl-test-db
```

Salvaguarda: si el nombre de la base de `DATABASE_URL` no termina en `test` (por ejemplo `test` o `retrogamelog_test`), pytest aborta con código 2 antes de tocar nada.

Si `DATABASE_URL` no está definida, los tests usan `postgresql+psycopg://test:test@localhost:55432/test` (el contenedor de arriba).

## Notas de diseño

- `play_setups.device_id` no tiene `ON DELETE`, pero su comprobación es diferida (`DEFERRABLE INITIALLY DEFERRED`). Así borrar un dispositivo con configuraciones falla (al hacer commit), y aun así borrar un usuario funciona: PostgreSQL revisa los dispositivos antes de que la cascada borre sus configuraciones, y con una comprobación inmediata eso fallaba.
- El email único sin distinguir mayúsculas es un índice sobre `lower(email)`; guardarlo en minúsculas es responsabilidad de la API.
