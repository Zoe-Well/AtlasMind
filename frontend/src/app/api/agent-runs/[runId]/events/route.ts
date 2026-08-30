import { backendFetch } from "@/lib/api/server";
import { serverSession } from "@/lib/auth/server-session";

export async function GET(
  request: Request,
  context: { params: Promise<{ runId: string }> },
) {
  const session = await serverSession();
  if (!session) return Response.json({ code: "UNAUTHENTICATED" }, { status: 401 });
  const { runId } = await context.params;

  const lastEventId = request.headers.get("last-event-id");
  const url = new URL(request.url);
  const after = url.searchParams.get("after");
  const suffix = after ? `?after=${encodeURIComponent(after)}` : "";
  const headers = new Headers({ accept: "text/event-stream" });
  if (lastEventId) headers.set("last-event-id", lastEventId);
  const response = await backendFetch(
    session,
    `/v1/agent-runs/${encodeURIComponent(runId)}/events${suffix}`,
    { headers },
  );
  if (!response.ok || !response.body) {
    return Response.json({ code: "AGENT_EVENT_STREAM_UNAVAILABLE" }, { status: response.status });
  }

  return new Response(response.body, {
    headers: {
      "content-type": "text/event-stream",
      "cache-control": "no-cache, no-transform",
      connection: "keep-alive",
      "x-accel-buffering": "no",
    },
  });
}
