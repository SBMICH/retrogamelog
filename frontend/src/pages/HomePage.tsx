import { ApiStatus } from "../components/ApiStatus";

export function HomePage() {
  return (
    <main className="page">
      <h1>RetroGameLog</h1>
      <p>Tu diario y catálogo de videojuegos retro.</p>
      <ApiStatus />
    </main>
  );
}
