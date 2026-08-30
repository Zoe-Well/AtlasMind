import "server-only";

import { backendApiUrl } from "@/lib/auth/config";
import type { PrivateSession } from "@/lib/auth/session";

export async function backendFetch(
  session: PrivateSession,
  path: string,
  init: RequestInit = {},
): Promise<Response> {
  const baseUrl = backendApiUrl();
  if (!baseUrl || !session.accessToken) {
    return Response.json(
      {
        type: "urn:atlasmind:error:backend-not-configured",
        title: "Backend API is not configured",
        status: 503,
        code: "BACKEND_NOT_CONFIGURED",
      },
      { status: 503 },
    );
  }
  const headers = new Headers(init.headers);
  headers.set("authorization", `Bearer ${session.accessToken}`);
  if (!headers.has("accept")) headers.set("accept", "application/json");
  return fetch(`${baseUrl}${path}`, { ...init, headers, cache: "no-store" });
}
