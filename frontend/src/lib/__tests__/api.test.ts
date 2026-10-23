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
  document.cookie = "vs_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/";
});

describe("api client", () => {
  it("GETs with credentials and serialises query params", async () => {
    const fetchMock = vi.fn<typeof fetch>(async () => jsonResponse({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);

    const result = await api.get<{ ok: boolean }>("/feed", { mode: "for_you", limit: 8 });

    expect(result).toEqual({ ok: true });
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(String(url)).toContain("/api/v1/feed?mode=for_you&limit=8");
    expect(init?.credentials).toBe("include");
  });

  it("echoes the CSRF cookie on unsafe methods", async () => {
    document.cookie = "vs_csrf=token-123; path=/";
    const fetchMock = vi.fn<typeof fetch>(async () => jsonResponse({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);

    await api.post("/videos/42/like");

    const init = fetchMock.mock.calls[0]![1]!;
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
      if (url.endsWith("/auth/refresh")) return jsonResponse({ ok: true, csrf_token: "csrf-token" });
      const likeCalls = attempts.filter((call) => call.endsWith("/videos/1/like")).length;
      return jsonResponse(likeCalls === 1 ? null : { liked: true }, likeCalls === 1 ? 401 : 200);
    });
    vi.stubGlobal("fetch", fetchMock as unknown as typeof fetch);

    const result = await api.post<{ liked: boolean }>("/videos/1/like");

    expect(result).toEqual({ liked: true });
    expect(attempts).toHaveLength(3); // like -> refresh -> like
    expect(attempts[1]).toContain("/auth/refresh");
  });

  it("uses the refresh response CSRF token when the API cookie is not readable", async () => {
    const requests: Array<[string, RequestInit | undefined]> = [];
    const fetchMock = vi.fn(async (input: string | URL, init?: RequestInit) => {
      requests.push([String(input), init]);
      return requests.length === 1
        ? jsonResponse(
            {
              error: {
                code: "bad_request",
                message: "Missing or invalid CSRF token.",
                details: { hint: "Send the vs_csrf cookie value back in the X-CSRF-Token header." },
              },
            },
            403,
          )
        : requests.length === 2
          ? jsonResponse({ csrf_token: "response-token" })
          : jsonResponse({ liked: true });
    });
    vi.stubGlobal("fetch", fetchMock as unknown as typeof fetch);

    await api.post<{ liked: boolean }>("/videos/1/like");

    expect(requests[1][0]).toContain("/auth/refresh");
    expect((requests[2][1]?.headers as Record<string, string>)["X-CSRF-Token"]).toBe("response-token");
  });
});