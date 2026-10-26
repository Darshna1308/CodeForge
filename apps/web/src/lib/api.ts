export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public details?: unknown, public retryAfter?: number) {
    super(message);
  }
}

export async function api<T>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const { json, headers, ...rest } = init;
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      credentials: "include", // httpOnly session cookie
      ...rest,
      headers: { ...(json !== undefined ? { "Content-Type": "application/json" } : {}), ...headers },
      body: json !== undefined ? JSON.stringify(json) : rest.body,
    });
  } catch {
    throw new ApiError(0, "network_error", "Cannot reach the CodeForge API");
  }
  if (res.status === 204) return undefined as T;
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    const err = body?.error ?? {};
    const retry = Number(res.headers.get("Retry-After") ?? "") || undefined;
    throw new ApiError(res.status, err.code ?? "http_error", err.message ?? res.statusText, err.details, retry);
  }
  return body as T;
}

export function newIdempotencyKey(): string {
  const bytes = new Uint8Array(12);
  crypto.getRandomValues(bytes);
  return "web-" + Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}
