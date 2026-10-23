import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, api } from "@/lib/api";

/** Fresh JSON Response helper (Node 18+/jsdom both expose Response). */
function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "vs_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT";
});

describe("api client", () => {
  it("GETs with credentials and serialises query params", async () => {
    const fetchMock = vi.fn(async () => jsonResponse({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);

    const result = await api.get<{ ok: boolean }>("/feed", { mode: "for_you", limit: 8 });

    expect(result).toEqual({ ok: true });
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/api/v1/feed?mode=for_you&limit=8");
    expect(init.credentials).toBe("include");
  });

  it("echoes the CSRF cookie on unsafe methods", async () => {
    document.cookie = "vs_csrf=token-123; path=/";
    const fetchMock = vi.fn(async () => jsonResponse({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);

    await api.post("/videos/42/like");

    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect((init.headers as Record<string, string>)["X-CSRF-Token"]).toBe("token-123");
  });

  it("throws ApiError with the backend envelope", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse({ error: { code: "not_found", message: "Video not found" } }, 404)),
    );

    const attempt = await api.get("/videos/nope").then(
      () => null,
      (error) => error,
    );
    expect(attempt).toBeInstanceOf(ApiError);
    expect((attempt as ApiError).status).toBe(404);
    expect((attempt as ApiError).code).toBe("not_found");
    expect((attempt as ApiError).message).toBe("Video not found");
  });

  it("silently refreshes once after a 401, then retries the original call", async () => {
    const attempts: string[] = [];
    const fetchMock = vi.fn(async (input: string | URL) => {
      const url = String(input);
      attempts.push(url);
      if (url.endsWith("/auth/refresh")) return jsonResponse({ ok: true });
      const likeCalls = attempts.filter((call) => call.endsWith("/videos/1/like")).length;
      return jsonResponse(likeCalls === 1 ? null : { liked: true }, likeCalls === 1 ? 401 : 200);
    });
    vi.stubGlobal("fetch", fetchMock as unknown as typeof fetch);

    const result = await api.post<{ liked: boolean }>("/videos/1/like");

    expect(result).toEqual({ liked: true });
    expect(attempts).toHaveLength(3); // like -> refresh -> like
    expect(attempts[1]).toContain("/auth/refresh");
  });
});