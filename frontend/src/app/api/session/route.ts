import { publicSession } from "@/lib/auth/session";
import { serverSession } from "@/lib/auth/server-session";

export async function GET() {
  const session = await serverSession();
  if (!session) {
    return Response.json({ authenticated: false }, { status: 401 });
  }
  return Response.json(publicSession(session), {
    headers: { "cache-control": "no-store" },
  });
}
