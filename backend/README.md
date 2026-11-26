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
| `RETROACHIEVEMENTS_API_KEY` | Solo para importar el catálogo | (tu clave de la API web; es un secreto) |

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

## Importar el catálogo (RetroAchievements)

`python -m app.importers` llena las tablas `platforms` y `games` con la [API web de RetroAchievements](https://api-docs.retroachievements.org/). La API de RetroGameLog nunca llama a este comando: se ejecuta a mano.

| Opción | Efecto |
|---|---|
| (ninguna) | Importa NES, SNES, Game Boy Advance y Mega Drive |
| `--consolas snes gba` | Importa solo esas. Admite los alias `nes`, `snes`, `gba`, `megadrive` (o `md`), el nombre exacto de la API entre comillas o su ID |
| `--simular` | Consulta la API y la base y muestra lo que haría, sin escribir |

No se importan los hacks (títulos con `~Hack~`) ni los subconjuntos de logros (`[Subset - ...]`), según la [convención de nombres de RetroAchievements](https://docs.retroachievements.org/guidelines/content/game-info-and-hub-guidelines.html). Los juegos caseros, prototipos, demos y sin licencia sí entran. El comando dice cuántos excluye, y con `--simular` muestra ejemplos. No borra juegos que ya estén guardados.

### Primera importación real

1. En tu cuenta de RetroAchievements, abre el [panel de control](https://retroachievements.org/controlpanel.php) y copia la clave de la API web (sección "Keys"). Es un secreto: no la escribas en archivos del repositorio, en commits ni en el frontend.
2. Desde `backend/`, con PostgreSQL en marcha, define la base y aplica las migraciones:

```powershell
$env:DATABASE_URL = "postgresql+psycopg://usuario:clave@localhost:5432/retrogamelog"
.\.venv\Scripts\alembic.exe upgrade head
```

3. Define la clave solo en esta terminal. `Read-Host` evita que quede en el historial de PowerShell:

```powershell
$env:RETROACHIEVEMENTS_API_KEY = Read-Host "Clave de la API de RetroAchievements"
```

4. Haz primero una simulación y revisa los totales:

```powershell
.\.venv\Scripts\python.exe -m app.importers --simular
```

5. Si el resultado es el esperado, importa y después borra la clave de la terminal:

```powershell
.\.venv\Scripts\python.exe -m app.importers
```

```powershell
Remove-Item Env:RETROACHIEVEMENTS_API_KEY
```

### Cómo se comporta

- **Llamadas:** una para la lista de consolas (de ahí salen los ID) y una por cada consola, con 1 segundo de pausa. La simulación hace las mismas llamadas, así que no la repitas sin necesidad: la API limita las peticiones y pide cachear sus respuestas (la copia es la propia base de datos).
- **Errores temporales** (fallos de red, 408, 429 y errores 5xx habituales): hasta 4 intentos por llamada, con esperas de 2, 4 y 8 segundos, o lo que pida la cabecera `Retry-After` hasta un máximo de 120. Los demás errores no se reintentan.
- **Repetir la importación** no duplica filas. Actualiza el nombre de la consola y el título, la consola y el icono de cada juego (sobrescribe cambios hechos a mano en esos campos). No borra juegos, no vacía valores y no toca `short_name`, `manufacturer`, `release_year`, `developer`, `cover_url` ni `details_fetched_at`.
- **Fallos a mitad:** cada consola se guarda en una transacción propia. Si una falla, no queda nada de ella, las anteriores se conservan y el comando indica cuáles faltan; vuelve a ejecutarlo con `--consolas` para esas.
- **Códigos de salida:** `0` correcto, `1` falló la API o la base, `2` configuración o argumentos incorrectos.
- **Qué no se guarda:** el importador no pide los hashes de ROMs ni guarda enlaces a ROMs. De cada juego lee solo su ID, título, consola e icono.

Antes de publicar la demo hay que confirmar con RetroAchievements (canal `#coders` de su Discord) que sus términos permiten guardar y mostrar estos datos en una app pública.

## Datos iniciales

Carga los catálogos compartidos de modelos de dispositivo (`device_models`) y emuladores (`emulators`). Desde `backend/`, con las migraciones ya aplicadas:

```powershell
$env:DATABASE_URL = "postgresql+psycopg://..."
.\.venv\Scripts\python.exe -m app.seeds
```

Se puede ejecutar las veces que haga falta: solo inserta lo que falta, y nunca modifica ni borra filas, incluidas las añadidas a mano. Dos nombres que solo se diferencian en mayúsculas o espacios se consideran el mismo. Como no modifica ni borra, cambiar un nombre en el archivo añade una fila nueva y deja la anterior; quitar una entrada del archivo no la quita de la base.

Los datos están en `app/seeds/catalog.json`. Para añadir un modelo o un emulador:

1. Verifica el nombre en el sitio oficial del fabricante o del proyecto.
2. Agrega la línea al archivo. Reglas:
   - Dispositivos: `brand` es la marca y `name` el nombre comercial completo, con la marca delante (`"Retroid Pocket 5"`, `"Anbernic RG35XX H"`). La excepción es Steam Deck, cuyo nombre no incluye a Valve.
   - Emuladores: el nombre como lo escribe el proyecto. Los núcleos de RetroArch van como `"RetroArch (Núcleo)"`.
3. Ejecuta el comando. Si el archivo tiene un error (JSON inválido, entradas repetidas, textos vacíos o demasiado largos), lo indica y no carga nada.

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
