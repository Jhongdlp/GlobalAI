export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public code?: string,
  ) {
    super(message);
  }
}

/** fetch a la API con el formato de error único del backend. Sin sesión → vuelve al login. */
export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`/api/v1${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init.headers },
    });
  } catch {
    throw new ApiError(0, "No pudimos conectar con el servidor. Revisa tu conexión.");
  }
  if (res.status === 401 && location.pathname !== "/") location.replace("/");
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new ApiError(res.status, body?.error?.message ?? "Algo salió mal. Inténtalo de nuevo.", body?.error?.code);
  }
  return (res.status === 204 ? undefined : await res.json()) as T;
}

export const esc = (s: string) =>
  s.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
