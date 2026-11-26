# Pruebas de la API con Postman

Esta colección prueba la API **en marcha**, como lo haría una aplicación. Complementa a los tests de pytest de `backend/`, que siguen siendo la verificación principal.

## Qué hay

| Ruta | Contenido |
|---|---|
| `collections/RetroGameLog/` | Una petición por archivo, con sus pruebas |
| `environments/local.environment.yaml` | La dirección de la API (`baseUrl`) |

Las peticiones se ejecutan en este orden:

| Petición | Comprueba |
|---|---|
| Salud | 200 en `/health` |
| Registro | 201, y que la respuesta no incluya la contraseña |
| Registro duplicado | 409 con el mismo correo en mayúsculas |
| Registro con clave insegura | 422, sin repetir la contraseña |
| Entrar | 200 y guarda el token |
| Mi cuenta | 200 con el token |
| Mi cuenta sin token | 401 |
| Bloqueo tras cinco fallos | cinco 401 y un 429 con `Retry-After` |

Cada ejecución inventa su propio usuario, correo y contraseña, así que se puede repetir sin limpiar nada. No hay claves ni contraseñas reales en estos archivos. Ojo: cada ejecución deja una cuenta de prueba en la base a la que apunte la API.

## Antes de ejecutarla

La API tiene que estar levantada en `http://127.0.0.1:8000` (ver el `README.md` principal).

## En la aplicación de Postman

1. Instala la aplicación de escritorio.
2. Abre la carpeta del repositorio como carpeta local (según la versión: "Open Folder" o crear un espacio de trabajo "From a local folder"). La aplicación puede pedir una cuenta.
3. Elige el entorno `local` y ejecuta la colección completa.

Para probar una sola petición, usa **Send**. Las que dependen de datos anteriores (por ejemplo "Mi cuenta") necesitan que antes se hayan ejecutado "Registro" y "Entrar". "Bloqueo tras cinco fallos" solo se repite sola al ejecutar la colección; con **Send** hay que pulsar seis veces.

Si la aplicación crea una carpeta `.postman/` con datos de tu cuenta, revísala antes de subirla.

## En la terminal

Con [Postman CLI](https://learning.postman.com/docs/postman-cli/postman-cli-installation/), desde la raíz del repositorio. Se fija la versión 1.88.0, la misma que usa el CI:

```powershell
npm install --prefix "$env:TEMP\postman-cli" --ignore-scripts postman-cli@1.88.0
```

```powershell
& "$env:TEMP\postman-cli\node_modules\.bin\postman.cmd" collection run postman/collections/RetroGameLog --environment postman/environments/local.environment.yaml --no-report-events
```

- **No la instales con `-g` sin `--ignore-scripts`.** El script de una instalación global añade texto a los archivos de instrucciones de asistentes de código de tu usuario (por ejemplo, `~/.claude/CLAUDE.md`).
- **Usa `--no-report-events`.** Sin esa opción la herramienta envía datos de las ejecuciones a Postman.
- No hace falta iniciar sesión ni una clave para ejecutar la colección desde los archivos.

## En GitHub Actions

`.github/workflows/api-tests.yml` levanta una base PostgreSQL desechable, aplica las migraciones, arranca la API y ejecuta la colección en cada PR y en cada push a `main`. Si una comprobación falla, el workflow falla. No usa secretos. Por ahora no es obligatorio para fusionar.
