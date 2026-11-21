from fastapi import FastAPI

app = FastAPI(
    title="RetroGameLog API",
    description="Diario y catálogo de videojuegos retro.",
    version="0.1.0",
)


@app.get("/health", tags=["sistema"])
def health() -> dict[str, str]:
    """Indica que la API está viva. Lo usará Render para comprobar el servicio."""
    return {"status": "ok"}
