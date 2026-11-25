# RetroGameLog - Frontend

Aplicación React (TypeScript) creada con Vite. Por ahora tiene una única pantalla de inicio que muestra el estado de la API consultando `GET /health`.

## Requisitos

- Node.js 22 o superior y npm.
- El backend en marcha (por defecto en `http://127.0.0.1:8000`) para ver el estado "API conectada".

## Instalación

```powershell
cd frontend
npm install
Copy-Item .env.example .env
```

El archivo `.env` está ignorado por Git. Variable disponible:

| Variable       | Por defecto             | Descripción        |
| -------------- | ----------------------- | ------------------ |
| `VITE_API_URL` | `http://127.0.0.1:8000` | URL base de la API |

## Ejecutar en desarrollo

```powershell
npm run dev
```

Abre la URL que muestra Vite (normalmente http://localhost:5173).

Nota: el navegador solo podrá leer la respuesta de la API si el backend permite CORS desde el origen del frontend. Si ves "API no disponible" con el backend en marcha, revisa la configuración de CORS del backend.

## Pruebas

```powershell
npm test
```

Los tests usan Vitest y Testing Library y simulan `fetch`, por lo que no necesitan el backend.

## Construir para producción

```powershell
npm run build
```

Comprueba los tipos y genera los archivos en `dist/`. Se puede previsualizar con `npm run preview`.

## Estructura

```
src/
  api/          cliente de la API (client.ts)
  components/   componentes reutilizables (ApiStatus)
  pages/        pantallas (HomePage)
  test/         configuración de tests
```

Las dependencias están fijadas a versiones exactas (`.npmrc` con `save-exact=true`).
