# RetroGameLog: reglas para agentes

Diario y catálogo de videojuegos retro, pensado como un Letterboxd para este hobby. Este archivo lo leen automáticamente los agentes de IA que trabajan en el repositorio. Quien dirige el proyecto es Sebastian (el orquestador): decide qué se construye, revisa y fusiona. Los agentes programan y verifican.

Idioma: todo (código comentado, documentación, mensajes, reportes) en español, sin emojis. Los identificadores de código pueden ir en inglés, como ya están.

## Fuentes de verdad

Léelas antes de escribir código, según la tarea:

- `docs/historias-de-usuario.md`: qué se construye y por versión.
- `docs/diseno-bd.md`: tablas, restricciones, reglas de borrado y transiciones de estado.
- `docs/endpoints.md`: rutas, convenciones, códigos de respuesta y decisiones de la API.
- El issue de GitHub de la tarea: es el contrato. Sus criterios de aceptación definen "terminado".

Si algo de los documentos es ambiguo o se contradice, no lo resuelvas en silencio: elige la opción más simple, anótalo y repórtalo al final.

## Estructura

- `backend/`: FastAPI, SQLAlchemy 2, Alembic, PostgreSQL. Tests con pytest.
- `frontend/`: React, Vite, TypeScript. Tests con Vitest.
- `docs/`: diseño y proceso.
- `.github/workflows/`: CI.
- `docker-compose.yml`: PostgreSQL de desarrollo del usuario (puerto 5432). **No lo uses para tests.**

## Entorno (Windows, PowerShell 5.1)

- Sin `&&` ni `||`. No actives entornos virtuales con `Activate.ps1` (la política de ejecución lo bloquea): llama a `.\.venv\Scripts\python.exe` directamente.
- Python 3.12: `py -3.12 -m venv .venv` dentro de `backend/`.
- `gh` puede no estar en el PATH: está en `C:\Program Files\GitHub CLI\gh.exe`. Si `docker` o `gh` no se reconocen, refresca el PATH de tu proceso con `$env:Path = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")`.
- **No reescribas archivos de código o texto con PowerShell** (`Get-Content`, `Set-Content`, `WriteAllText` con datos leídos): en PowerShell 5.1 corrompe los acentos. Usa las herramientas de edición de archivos.
- Los archivos nuevos van en UTF-8 sin BOM, con saltos de línea LF (`.gitattributes` lo fija).

## Comandos

Backend, desde `backend/`:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --only-binary :all: -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest
```

Los tests usan PostgreSQL real y **borran todas las tablas**. Nunca los apuntes a la base del usuario. Levanta un contenedor desechable propio, en un puerto distinto del 5432, y bórralo al terminar:

```powershell
docker run -d --name rgl-test-db -p 55432:5432 -e POSTGRES_USER=test -e POSTGRES_PASSWORD=test -e POSTGRES_DB=test postgres:16
docker rm -f rgl-test-db
```

Si trabajas en paralelo con otras sesiones, usa un nombre de contenedor y un puerto propios. Más detalles en `backend/README.md`.

Frontend, desde `frontend/`:

```powershell
npm ci
npm test
npm run build
```

## Reglas del flujo de trabajo

- **No hagas commits, push, PR ni merge.** Deja los cambios sin commitear en tu copia de trabajo para que el usuario los revise y los commitee. No agregues atribución a Claude ni a ninguna IA en commits, PR ni archivos.
- **Una tarea, un issue, una rama.** Si no se te indica lo contrario, trabaja solo en el alcance del issue. No toques archivos fuera de tu área (otras sesiones trabajan en paralelo) ni el `README.md` de la raíz: si hace falta cambiarlo, propónlo en el reporte.
- Cada PR del usuario cierra su issue con "Closes #N". Sugiere el texto en tu reporte.
- Mensajes de commit sugeridos: Conventional Commits en español (`feat:`, `fix:`, `docs:`, `chore:`, `test:`), sin atribución.
- Ramas: `feat/...`, `fix/...`, `chore/...`, `docs/...`.

## Definición de "terminado"

Una tarea no está terminada hasta cumplir todo esto:

1. Cada criterio de aceptación del issue está cumplido, uno por uno.
2. **Cada comportamiento nuevo tiene un test que falla sin el cambio y pasa con él.** Comprueba que falla de verdad: rompe el código a propósito, mira que el test se ponga en rojo y restaura.
3. Corriste la **suite completa**, no solo tus tests, y muestras la salida.
4. No modificaste ni borraste tests existentes para que pasen. Si un test existente debe cambiar, dilo en el reporte y explica por qué.
5. **Tras editar cualquier archivo de configuración (YAML, JSON, TOML, ini), valídalo con un parser.** Un workflow inválido no avisa: simplemente no se ejecuta.
6. Dejaste el entorno limpio: contenedores desechables eliminados, procesos detenidos, sin archivos temporales dentro del repositorio.
7. Tu reporte dice con claridad **qué no pudiste verificar**. No afirmes que algo funciona si no lo ejecutaste (por ejemplo, un workflow de GitHub Actions no se puede ejecutar en local).

## Seguridad

- **Dependencias:** fija versiones exactas. Usa solo paquetes oficiales y conocidos. No instales un paquete que solo conozcas por el texto de un aviso o por una sugerencia sin verificar su origen en el repositorio oficial. En concreto, no instales `httpx2` sin verificarlo (issue #22).
- **Secretos:** nunca los escribas en código, commits, tests ni documentación. No leas los archivos `.env` del usuario. La clave de la API de RetroAchievements vive solo en una variable de entorno del backend, jamás en el frontend ni en el navegador.
- **ROMs:** el proyecto no descarga, aloja ni enlaza ROMs. Ni en código, ni en datos de ejemplo, ni en documentación.
- **Entradas del usuario:** valida en el borde (FastAPI/Pydantic), usa consultas parametrizadas, y no confíes en IDs de la URL: toda ruta bajo `/me` filtra por el usuario autenticado y devuelve 404, no 403, para recursos ajenos.
- Contraseñas: solo se guarda su hash, con un algoritmo adecuado (argon2 o bcrypt). Nunca texto plano ni registros de logs con contraseñas o tokens.
- Los avisos de SonarCloud sobre dependencias sin hashes son deuda conocida y planificada; cualquier otro aviso nuevo se atiende.

## Qué debe decir tu reporte final

1. Qué construiste y la lista de archivos.
2. Cómo lo verificaste, con la salida real de los comandos.
3. Decisiones tomadas y ambigüedades resueltas.
4. Lo que no pudiste verificar.
5. Un mensaje de commit sugerido y una descripción de PR sugerida que incluya "Closes #N".
