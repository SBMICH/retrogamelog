import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiStatus } from "./ApiStatus";

function mockFetch(impl: () => Promise<Partial<Response>>) {
  vi.stubGlobal("fetch", vi.fn(impl));
}

describe("ApiStatus", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("muestra el estado de carga al inicio", () => {
    mockFetch(() => new Promise(() => {}));
    render(<ApiStatus />);
    expect(screen.getByRole("status")).toHaveTextContent("Comprobando la API");
  });

  it("muestra API conectada cuando /health responde bien", async () => {
    mockFetch(async () => ({ ok: true, json: async () => ({ status: "ok" }) }));
    render(<ApiStatus />);
    expect(await screen.findByText("API conectada")).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith(
      expect.stringMatching(/\/health$/),
      expect.anything(),
    );
  });

  it("muestra API no disponible cuando la red falla", async () => {
    mockFetch(async () => {
      throw new TypeError("Failed to fetch");
    });
    render(<ApiStatus />);
    expect(await screen.findByText("API no disponible")).toBeInTheDocument();
  });

  it("muestra API no disponible cuando la API responde con error", async () => {
    mockFetch(async () => ({ ok: false, status: 500 }));
    render(<ApiStatus />);
    expect(await screen.findByText("API no disponible")).toBeInTheDocument();
    expect(screen.getByText(/código 500/)).toBeInTheDocument();
  });
});
