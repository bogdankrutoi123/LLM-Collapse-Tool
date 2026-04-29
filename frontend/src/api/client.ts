const DEFAULT_BASE_URL = "http://localhost:8000";

function getBaseUrl() {
  return import.meta.env.VITE_API_BASE_URL || DEFAULT_BASE_URL;
}

function getDetailFromPayload(payload: unknown): string | null {
  if (typeof payload === "string") return payload;
  if (!payload || typeof payload !== "object") return null;
  const detail = (payload as { detail?: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object") {
    try { return JSON.stringify(detail); } catch { return null; }
  }
  return null;
}

async function extractErrorMessage(res: Response): Promise<string> {
  const text = await res.text();
  if (!text) return `Request failed (${res.status} ${res.statusText})`;
  try {
    const payload = JSON.parse(text);
    return getDetailFromPayload(payload) || text;
  } catch {
    return text;
  }
}

function asNetworkErrorMessage(error: unknown): string {
  if (error instanceof TypeError) {
    return "NetworkError: failed to reach API server. Check backend availability and CORS/base URL configuration.";
  }
  return error instanceof Error ? error.message : "Request failed";
}

let unauthorizedHandler: (() => void) | null = null;

export function setUnauthorizedHandler(fn: () => void) {
  unauthorizedHandler = fn;
}

async function fetchWithRetry(path: string, options: RequestInit = {}, retried = false): Promise<Response> {
  let res: Response;
  try {
    res = await fetch(`${getBaseUrl()}${path}`, {
      ...options,
      credentials: "include",
    });
  } catch (error) {
    throw new Error(asNetworkErrorMessage(error));
  }

  if (res.status === 401 && !retried && path !== "/api/v1/auth/refresh") {
    try {
      const refreshRes = await fetch(`${getBaseUrl()}/api/v1/auth/refresh`, {
        method: "POST",
        credentials: "include",
      });
      if (refreshRes.ok) {
        return fetchWithRetry(path, options, true);
      }
    } catch {
      // fall through
    }
    if (unauthorizedHandler) unauthorizedHandler();
  }

  return res;
}

export async function apiFetch<T>(path: string, options: RequestInit = {}) {
  const headers = new Headers(options.headers || {});
  headers.set("Content-Type", "application/json");

  const res = await fetchWithRetry(path, { ...options, headers });

  if (!res.ok) {
    throw new Error(await extractErrorMessage(res));
  }
  if (res.status === 204) return null as T;
  const text = await res.text();
  if (!text) return null as T;
  return JSON.parse(text) as T;
}

export async function apiDownload(path: string, options: RequestInit = {}) {
  const headers = new Headers(options.headers || {});
  if (options.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const res = await fetchWithRetry(path, { ...options, headers });
  if (!res.ok) throw new Error(await extractErrorMessage(res));
  return res.blob();
}

export async function apiUpload<T>(path: string, formData: FormData, options: RequestInit = {}) {
  const res = await fetchWithRetry(path, {
    ...options,
    method: options.method || "POST",
    body: formData,
  });
  if (!res.ok) throw new Error(await extractErrorMessage(res));
  if (res.status === 204) return null as T;
  const text = await res.text();
  if (!text) return null as T;
  return JSON.parse(text) as T;
}
