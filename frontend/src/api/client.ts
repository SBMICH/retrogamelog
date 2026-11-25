const DEFAULT_API_URL = "http://127.0.0.1:8000";

export const API_URL: string = (
  import.meta.env.VITE_API_URL || DEFAULT_API_URL
).replace(/\/+$/, "");

export interface HealthResponse {
  status: string;
}

/** Consulta GET /health. Lanza un Error si la API no responde o responde con error. */
export async function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  const response = await fetch(`${API_URL}/health`, { signal });
  if (!response.ok) {
    throw new Error(`La API respondió con el código ${response.status}`);
  }
  return (await response.json()) as HealthResponse;
}
