// Tiny fetch wrapper for the local API served by `careeros ui`. Mutations carry `X-CareerOS: 1`: the server
// refuses state-changing requests without it (a page on another site can't set custom headers cross-origin).

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public body: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function detailOf(body: unknown, status: number): string {
  if (body && typeof body === "object" && "detail" in body) {
    const d = (body as { detail: unknown }).detail;
    return typeof d === "string" ? d : JSON.stringify(d);
  }
  return `Request failed (${status})`;
}

async function parse(res: Response): Promise<unknown> {
  const text = await res.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(path, { ...init, headers: { Accept: "application/json", ...init.headers } });
  const body = await parse(res);
  if (!res.ok) throw new ApiError(res.status, detailOf(body, res.status), body);
  return body as T;
}

export function apiSend<T>(method: "POST" | "PUT" | "PATCH" | "DELETE", path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { "X-CareerOS": "1" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  return apiFetch<T>(path, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}
