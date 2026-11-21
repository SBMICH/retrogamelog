# RetroGameLog

RetroGameLog es un diario y catálogo de videojuegos retro, pensado como un Letterboxd para este hobby. Permite llevar el registro de lo que has jugado, lo que estás jugando y lo que quieres jugar después, con tu calificación, tus notas y el dispositivo y emulador en que corrió cada juego.

El proyecto nace de una dificultad real: entrar al mundo retro es abrumador, y encontrar buenos juegos toma mucho más tiempo del necesario. Tener un registro ordenado ayuda a mirar atrás, planear lo que viene y no perderse entre tantas posibilidades.

A futuro, la meta es construir una comunidad donde los jugadores compartan reseñas y listas, y donde quien empieza pueda descubrir juegos más rápido.

RetroGameLog no descarga, aloja ni enlaza ROMs.

## Estado

En desarrollo. Etapa actual: definición y diseño (versión 0.1).

## Hoja de ruta

| Versión | Contenido |
|---|---|
| v0.1 | Cuenta, catálogo de juegos, registro personal, dispositivos y estadísticas |
| v0.2 | Comunidad: perfiles públicos, reseñas, listas, seguir a otros |
| v0.3 | Descubrimiento para quien empieza: listas curadas, juegos que corren bien en tu dispositivo |
| v0.4 | Sincronización con RetroAchievements |

Las historias de usuario están en [docs/historias-de-usuario.md](docs/historias-de-usuario.md).

## Desarrollo local

Requisitos: [Docker Desktop](https://www.docker.com/products/docker-desktop/) y Python 3.12.

1. Clona el repositorio y entra a la carpeta del proyecto.
2. Crea tu archivo de configuración a partir de la plantilla y cambia la contraseña:

   ```powershell
   Copy-Item .env.example .env
   ```

   En Linux o macOS: `cp .env.example .env`. El archivo `.env` está en `.gitignore` y nunca se sube al repositorio.

3. Levanta la base de datos PostgreSQL:

   ```
   docker compose up -d
   ```

4. Comprueba que esté lista (el estado debe ser `healthy`):

   ```
   docker compose ps
   ```

5. Para detenerla sin perder los datos, usa `docker compose down`. Para borrar también los datos, `docker compose down -v`.

Las instrucciones para ejecutar el backend se agregarán cuando exista.

## Stack previsto

- Backend: FastAPI, PostgreSQL, autenticación con JWT
- Frontend: React
- Infraestructura: Docker Compose, GitHub Actions, SonarCloud
- Despliegue: Render
