# Endpoints de la API (v0.1)

API REST con FastAPI. Documentación interactiva generada automáticamente en `/docs`.

## Convenciones

- **Prefijo:** todas las rutas empiezan con `/api/v1`. El número de versión permite cambiar la API más adelante sin romper clientes existentes.
- **Formato:** JSON en peticiones y respuestas.
- **Autenticación:** JWT en la cabecera `Authorization: Bearer <token>`. Las rutas marcadas con "Sí" en la columna Auth lo requieren.
- **Datos propios bajo `/me`:** las rutas del usuario no llevan su ID en la URL. El backend sabe quién es por el token, así nadie puede pedir los datos de otro cambiando un número en la URL.
- **Paginación:** los listados aceptan `page` (desde 1) y `size` (por defecto 20, máximo 100) y responden con `{ "items": [...], "total": n, "page": p, "size": s }`.
- **Nombres:** recursos en plural y en inglés (`games`, `devices`), con guiones si son compuestos (`device-models`).

## Códigos de respuesta

| Código | Cuándo |
|---|---|
| 200 OK | Lectura o actualización correcta |
| 201 Created | Se creó un recurso |
| 204 No Content | Se borró un recurso |
| 400 Bad Request | Petición inválida por una regla de negocio (ej.: el dispositivo no es tuyo) |
| 401 Unauthorized | Falta el token o no es válido |
| 404 Not Found | No existe, o pertenece a otro usuario (no se revela cuál de las dos) |
| 409 Conflict | Duplicado (ej.: email ya registrado, juego ya en tu registro) |
| 429 Too Many Requests | Demasiados intentos de inicio de sesión fallidos con un correo |
| 422 Unprocessable Entity | Datos con formato incorrecto (lo genera FastAPI automáticamente) |

## Sistema

| Método | Ruta | Auth | Descripción |
|---|---|---|---|
| GET | `/health` | No | Comprueba que la API está viva. Útil para Render |

## Autenticación y cuenta (H1)

| Método | Ruta | Auth | Descripción |
|---|---|---|---|
| POST | `/api/v1/auth/register` | No | Crea una cuenta. Cuerpo: `email`, `username` (nombre público), `password`. El email se guarda en minúsculas. La contraseña tiene de 8 a 128 caracteres, con letra y número, no es común ni contiene el username o el correo (422 si no cumple). 409 si el email o el username ya existen. Responde 201 con el usuario (sin contraseña) |
| POST | `/api/v1/auth/login` | No | Inicia sesión con **email y contraseña**. Se envía como formulario (flujo OAuth2 password); el campo del formulario se llama `username` por el estándar, pero lleva el email. Devuelve `{ "access_token": "...", "token_type": "bearer" }`. Tras 5 fallos con un mismo correo responde 429 con `Retry-After` durante 15 minutos |
| GET | `/api/v1/me` | Sí | Datos del usuario autenticado |

## Catálogo (H2, H3)

Solo lectura para los usuarios. Se llena con scripts de importación.

| Método | Ruta | Auth | Descripción |
|---|---|---|---|
| GET | `/api/v1/platforms` | No | Lista de consolas |
| GET | `/api/v1/genres` | No | Lista de géneros |
| GET | `/api/v1/games` | No | Busca juegos. Filtros: `q` (título), `platform_id`, `genre_id`, `year`. Paginado |
| GET | `/api/v1/games/{game_id}` | No | Ficha de un juego con lo que ya está guardado. Es solo lectura: nunca llama a la API externa. Si `details_fetched_at` es `null`, la ficha aún no tiene carátula, género, año ni desarrollador |
| POST | `/api/v1/games/{game_id}/details` | Sí | Descarga los detalles del juego desde RetroAchievements y los guarda. Si ya estaban guardados, responde con ellos sin llamar a la API. Bloquea la fila mientras descarga para que dos peticiones simultáneas no hagan dos llamadas. Tiene límite de peticiones por usuario. El frontend lo llama cuando la ficha llega sin detalles |
| GET | `/api/v1/device-models` | No | Lista de modelos de dispositivo |
| GET | `/api/v1/emulators` | No | Lista de emuladores |

## Mi registro (H4, H5, H7)

| Método | Ruta | Auth | Descripción |
|---|---|---|---|
| GET | `/api/v1/me/games` | Sí | Mis juegos. Filtros: `status`, `platform_id`. Orden: `sort` (`updated`, `title`, `rating`, `priority`). Paginado |
| POST | `/api/v1/me/games` | Sí | Agrega un juego a mi registro. Cuerpo: `game_id`, `status`, y opcionales `status_date` (fecha en que empezó, terminó o abandonó el juego; por defecto, hoy), `rating`, `notes`, `priority`. Crea la entrada de historial que corresponda (ver tabla de transiciones en `diseno-bd.md`). 409 si ya lo tengo |
| GET | `/api/v1/me/games/{user_game_id}` | Sí | Detalle de un juego de mi registro, con su historial y sus configuraciones |
| PATCH | `/api/v1/me/games/{user_game_id}` | Sí | Cambia estado, calificación, notas o prioridad. Si cambia `status`, acepta `status_date` (por defecto, hoy) y crea la entrada de historial que indica la tabla de transiciones de `diseno-bd.md` |
| DELETE | `/api/v1/me/games/{user_game_id}` | Sí | Quita el juego de mi registro, con su historial y configuraciones |

## Historial (H6)

| Método | Ruta | Auth | Descripción |
|---|---|---|---|
| GET | `/api/v1/me/log` | Sí | Mi historial completo en orden cronológico inverso. Filtros: `from`, `to` (fechas), `kind`. Paginado |
| POST | `/api/v1/me/games/{user_game_id}/log` | Sí | Agrega una entrada manual (ej.: una rejugada o una nota con fecha) |
| PATCH | `/api/v1/me/log/{entry_id}` | Sí | Corrige fecha o nota de una entrada |
| DELETE | `/api/v1/me/log/{entry_id}` | Sí | Borra una entrada |

## Dispositivos y configuraciones (H8)

| Método | Ruta | Auth | Descripción |
|---|---|---|---|
| GET | `/api/v1/me/devices` | Sí | Mis dispositivos |
| POST | `/api/v1/me/devices` | Sí | Agrega un dispositivo. Cuerpo: `device_model_id`, `nickname` opcional |
| PATCH | `/api/v1/me/devices/{device_id}` | Sí | Cambia el apodo o el modelo |
| DELETE | `/api/v1/me/devices/{device_id}` | Sí | Borra un dispositivo. 409 si tiene configuraciones asociadas |
| POST | `/api/v1/me/games/{user_game_id}/setups` | Sí | Registra cómo corrió un juego. Cuerpo: `device_id`, `emulator_id` opcional, `performance`, `comment` opcional. 400 si el dispositivo no es mío |
| PATCH | `/api/v1/me/setups/{setup_id}` | Sí | Corrige una configuración |
| DELETE | `/api/v1/me/setups/{setup_id}` | Sí | Borra una configuración |

Las configuraciones de un juego se leen dentro de `GET /api/v1/me/games/{user_game_id}`.

## Estadísticas y sugerencia (H9, H10)

| Método | Ruta | Auth | Descripción |
|---|---|---|---|
| GET | `/api/v1/me/stats` | Sí | Totales por estado, juegos por consola, terminados por año y calificación media |
| GET | `/api/v1/me/suggestion` | Sí | Sugiere un juego de mi backlog, al azar con más peso para la prioridad alta. Filtro opcional: `platform_id`. 404 si el backlog está vacío |

## Decisiones

1. **Solo token de acceso en la v0.1, sin token de refresco.** El token dura un tiempo limitado (por ejemplo 60 minutos) y luego hay que volver a iniciar sesión. Los tokens de refresco se pueden añadir después sin romper nada.
2. **Login con email, enviado como formulario OAuth2.** Es lo que FastAPI espera para que el botón "Authorize" de `/docs` funcione, y facilita probar la API a mano. El estándar llama `username` al campo, pero en esta API lleva el email. El username público es otra cosa y se elige al registrarse.
6. **Los GET nunca escriben ni llaman a APIs externas.** La descarga de detalles de un juego es un POST autenticado y con límite de peticiones, para que nadie pueda agotar la cuota de RetroAchievements desde fuera.
3. **404 en lugar de 403 para recursos ajenos.** Así no se revela que existe un registro con ese ID.
4. **Rutas cortas para editar y borrar** (`/me/log/{entry_id}`, `/me/setups/{setup_id}`): el ID ya identifica el recurso, no hace falta anidarlo bajo el juego.
5. **Las rutas públicas de la v0.2** (perfiles, reseñas, listas) irán bajo `/api/v1/users/{username}/...` y no chocan con estas.
