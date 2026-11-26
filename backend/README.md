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
| `JWT_SECRET` | Sí, para la API | cadena aleatoria de 32 caracteres o más (ver abajo) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | No | `60` (por defecto) |
| `CORS_ORIGINS` | No | `https://retrogamelog.example,https://www.retrogamelog.example` |

`CORS_ORIGINS` es la lista (separada por comas) de orígenes del frontend a los que el navegador deja llamar a la API. Si no se define, se usan los de desarrollo local (`http://localhost:5173` y `http://127.0.0.1:5173`). No se admite `*`, y cada origen debe empezar por `http://` o `https://`. En producción hay que definirla con la URL real del frontend.

`JWT_SECRET` firma los tokens de sesión. No tiene valor por defecto: si falta o tiene menos de 32 caracteres, la API no arranca. Genera uno con:

```powershell
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
```

Usa un secreto distinto en cada entorno y no lo guardes en el repositorio. Cambiarlo invalida todos los tokens emitidos. Las migraciones no lo necesitan.

`ACCESS_TOKEN_EXPIRE_MINUTES` es la duración de cada token: un entero entre 1 y 10080 (una semana).

La aplicación no lee archivos `.env`: las variables tienen que estar en el entorno del proceso.

## Arrancar la API en local

Primero levanta la base de datos de desarrollo desde la raíz del repositorio (ver el `README.md` principal): `docker compose up -d`. Luego, desde `backend/` y con el usuario, la contraseña y la base de tu archivo `.env`:

```powershell
$env:DATABASE_URL = "postgresql+psycopg://usuario:clave@localhost:5432/retrogamelog"
$env:JWT_SECRET = .\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Con este método el secreto dura lo que la ventana de PowerShell: al abrir otra se genera uno nuevo y hay que iniciar sesión otra vez.

La documentación interactiva queda en `http://127.0.0.1:8000/docs`.

## Autenticación

| Método | Ruta | Descripción |
|---|---|---|
| POST | `/api/v1/auth/register` | JSON con `email`, `username` y `password`. 201, 409 (duplicado) o 422 |
| POST | `/api/v1/auth/login` | Formulario OAuth2; `username` lleva el email. 200 con `access_token`, o 401 |
| GET | `/api/v1/me` | Datos propios. Requiere `Authorization: Bearer <token>` |

Para probar en `/docs`: registra una cuenta, pulsa **Authorize**, escribe el email en `username` y la contraseña (deja `client_id` y `client_secret` vacíos) y llama a `GET /api/v1/me`.

Cómo funciona:

- `username`: de 3 a 30 caracteres entre letras sin acentos, números, `_` y `-`. Contraseña: de 8 a 128 caracteres. El email se guarda en minúsculas.
- Las contraseñas se guardan solo como hash argon2id.
- Los tokens son JWT firmados con HS256 (el algoritmo lo fija el servidor), con `sub` (ID del usuario) y `exp`.
- Las respuestas 422 de toda la API indican `type`, `loc` y `msg`, pero no repiten lo que envió el cliente.

Para una ruta nueva bajo `/me`, pide la dependencia `CurrentUser` (en `app/api/deps.py`), filtra las consultas por `user.id` y responde 404 ante recursos ajenos. Los routers se registran en `app/api/router.py`.

No actives el nivel `DEBUG` del registro `sqlalchemy.engine` con datos reales: imprime las filas leídas, incluidos los hashes de contraseñas.

## Deuda conocida

- No hay límite de intentos de inicio de sesión ni de registros. Además de permitir adivinar contraseñas, cada intento calcula un hash argon2 que usa 64 MiB de memoria, así que muchas peticiones simultáneas pueden agotar un servidor pequeño. Hay que resolverlo antes de exponer la API en público.
- El registro responde 409 si el email ya existe (lo pide el contrato), así que permite averiguar qué emails tienen cuenta.
- No hay token de refresco, ni cierre de sesión que revoque tokens, ni recuperación de contraseña, ni verificación de correo.

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
