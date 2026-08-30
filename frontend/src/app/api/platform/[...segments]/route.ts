import { backendFetch } from "@/lib/api/server";
import { serverSession } from "@/lib/auth/server-session";

interface RouteContext {
  params: Promise<{ segments: string[] }>;
}

async function handle(request: Request, context: RouteContext) {
  const session = await serverSession();
  if (!session) return Response.json({ code: "UNAUTHENTICATED" }, { status: 401 });
  const { segments } = await context.params;
  const headers = new Headers(request.headers);
  headers.delete("authorization");
  headers.delete("cookie");
  headers.delete("connection");
  headers.delete("content-length");
  headers.delete("host");
  const body = request.method === "GET" || request.method === "HEAD" ? undefined : await request.arrayBuffer();
  const query = new URL(request.url).search;
  return backendFetch(session, `/v1/${segments.map(encodeURIComponent).join("/")}${query}`, {
    method: request.method,
    headers,
    body,
  });
}

export const GET = handle;
export const POST = handle;
export const PUT = handle;
export const DELETE = handle;
