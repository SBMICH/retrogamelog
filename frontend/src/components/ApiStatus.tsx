import { useEffect, useState } from "react";
import { getHealth } from "../api/client";

type Status = "loading" | "connected" | "unavailable";

const LABELS: Record<Status, string> = {
  loading: "Comprobando la API…",
  connected: "API conectada",
  unavailable: "API no disponible",
};

export function ApiStatus() {
  const [status, setStatus] = useState<Status>("loading");
  const [detail, setDetail] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    getHealth(controller.signal)
      .then(() => setStatus("connected"))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setStatus("unavailable");
        setDetail(error instanceof Error ? error.message : "Error desconocido");
      });
    return () => controller.abort();
  }, []);

  return (
    <section aria-labelledby="api-status-title" className="api-status">
      <h2 id="api-status-title">Estado de la API</h2>
      <p role="status" className={`badge badge-${status}`}>
        {LABELS[status]}
      </p>
      {status === "unavailable" && (
        <p className="detail">
          No se pudo contactar con el servidor. Comprueba que el backend está
          en marcha. {detail}
        </p>
      )}
    </section>
  );
}
