/**
 * Typed API client.
 *
 * - The session rides in HttpOnly cookies, so every request uses credentials: "include".
 * - State-changing requests echo the readable `vs_csrf` cookie in `X-CSRF-Token`
 *   (double-submit protection).
 * - A 401 is retried once after a silent token refresh; if that fails the caller sees
 *   the error and the UI routes to /login.
 */

const API_BASE: string = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1").replace(/\/+$/, "");
export const WS_BASE: string = (import.meta.env.VITE_WS_BASE_URL ?? "ws://localhost:8000/ws").replace(/\/+$/, "");
export const APP_NAME: string = import.meta.env.VITE_APP_NAME ?? "VibeSpace";

type Json = Record<string, unknown> | unknown[] | string | number | boolean | null;

export class ApiError extends Error {
  status: number;
  code: string;
  details?: Record<string, unknown>;

  constructor(status: number, code: string, message: string, details?: Record<string, unknown>) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

function readCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

const UNSAFE = new Set(["POST", "PUT", "PATCH", "DELETE"]);
const NO_REFRESH = ["/auth/login", "/auth/register", "/auth/refresh", "/auth/password"];

interface RequestOptions {
  method?: string;
  body?: unknown;
  query?: Record<string, string | number | boolean | undefined | null>;
  signal?: AbortSignal;
  skipRefresh?: boolean;
}

function buildUrl(path: string, query?: RequestOptions["query"]): string {
  const url = new URL(`${API_BASE}${path.startsWith("/") ? path : `/${path}`}`);
  if (query) {
    Object.entries(query).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") url.searchParams.set(key, String(value));
    });
  }
  return url.toString();
}

async function parseResponse(response: Response): Promise<Json> {
  if (response.status === 204) return null;
  const text = await response.text();
  if (!text) return null;
  try {
    return JSON.parse(text) as Json;
  } catch {
    return text;
  }
}

export async function rawRequest<T = Json>(path: string, options: RequestOptions = {}): Promise<T> {
  const method = (options.method ?? "GET").toUpperCase();
  const headers: Record<string, string> = { Accept: "application/json" };

  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  if (UNSAFE.has(method)) {
    const token = readCookie("vs_csrf");
    if (token) headers["X-CSRF-Token"] = token;
  }

  const response = await fetch(buildUrl(path, options.query), {
    method,
    headers,
    credentials: "include",
    signal: options.signal,
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
  });

  if (response.status === 401 && !options.skipRefresh && !NO_REFRESH.some((prefix) => path.startsWith(prefix))) {
    const refreshed = await tryRefresh();
    if (refreshed) {
      return rawRequest<T>(path, { ...options, skipRefresh: true });
    }
  }

  const payload = await parseResponse(response);

  if (!response.ok) {
    const envelope = payload as { error?: { code?: string; message?: string; details?: Record<string, unknown> } };
    throw new ApiError(
      response.status,
      envelope?.error?.code ?? "request_failed",
      envelope?.error?.message ?? `Request failed (${response.status}).`,
      envelope?.error?.details,
    );
  }

  return payload as T;
}

let refreshInFlight: Promise<boolean> | null = null;

async function tryRefresh(): Promise<boolean> {
  if (!refreshInFlight) {
    refreshInFlight = rawRequest("/auth/refresh", { method: "POST", skipRefresh: true })
      .then(() => true)
      .catch(() => false)
      .finally(() => {
        refreshInFlight = null;
      });
  }
  return refreshInFlight;
}

export const api = {
  get: <T = Json>(path: string, query?: RequestOptions["query"], signal?: AbortSignal) =>
    rawRequest<T>(path, { query, signal }),
  post: <T = Json>(path: string, body?: unknown, query?: RequestOptions["query"]) =>
    rawRequest<T>(path, { method: "POST", body, query }),
  patch: <T = Json>(path: string, body?: unknown, query?: RequestOptions["query"]) =>
    rawRequest<T>(path, { method: "PATCH", body, query }),
  put: <T = Json>(path: string, body?: unknown) => rawRequest<T>(path, { method: "PUT", body }),
  del: <T = Json>(path: string, query?: RequestOptions["query"]) =>
    rawRequest<T>(path, { method: "DELETE", query }),
};

/** Upload a file straight to object storage with a short-lived presigned URL. */
export async function putToStorage(
  uploadUrl: string,
  file: File,
  contentType: string,
  onProgress?: (percent: number) => void,
): Promise<void> {
  await new Promise<void>((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open("PUT", uploadUrl, true);
    request.setRequestHeader("Content-Type", contentType);
    request.upload.onprogress = (event) => {
      if (event.lengthComputable && onProgress) onProgress(Math.round((event.loaded / event.total) * 100));
    };
    request.onload = () =>
      request.status >= 200 && request.status < 300
        ? resolve()
        : reject(new ApiError(request.status, "upload_failed", `Storage rejected the upload (${request.status}).`));
    request.onerror = () =>
      reject(new ApiError(0, "upload_failed", "The upload could not reach object storage. Check S3/CORS settings."));
    request.send(file);
  });
}

export { API_BASE };