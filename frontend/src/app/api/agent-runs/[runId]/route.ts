import { backendFetch } from "@/lib/api/server";
import { serverSession } from "@/lib/auth/server-session";

export async function GET(
  _request: Request,
  context: { params: Promise<{ runId: string }> },
) {
  const session = await serverSession();
  if (!session) return Response.json({ code: "UNAUTHENTICATED" }, { status: 401 });
  const { runId } = await context.params;
  return backendFetch(session, `/v1/agent-runs/${encodeURIComponent(runId)}`);
}
