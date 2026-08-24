import { backendFetch } from "@/lib/api/server";
import { serverSession } from "@/lib/auth/server-session";

const encoder = new TextEncoder();
const terminalStates = new Set(["COMPLETED", "PARTIAL", "FAILED", "TIMED_OUT", "CANCELLED"]);

function event(data: unknown) {
  return encoder.encode(`data: ${JSON.stringify(data)}\n\n`);
}

export async function GET(
  _request: Request,
  context: { params: Promise<{ runId: string }> },
) {
  const session = await serverSession();
  if (!session) return Response.json({ code: "UNAUTHENTICATED" }, { status: 401 });
  const { runId } = await context.params;

  const stream = new ReadableStream({
    async start(controller) {
      try {
        for (let attempt = 0; attempt < 60; attempt += 1) {
          const response = await backendFetch(
            session,
            `/v1/agent-runs/${encodeURIComponent(runId)}`,
          );
          if (!response.ok) throw new Error("AgentRun unavailable");
          const run = await response.json();
          controller.enqueue(event(run));
          if (terminalStates.has(run.state)) break;
          await new Promise((resolve) => setTimeout(resolve, 1000));
        }
      } catch {
        controller.enqueue(
          event({ state: "FAILED", failure: { code: "SOURCE_UNAVAILABLE" } }),
        );
      } finally {
        controller.close();
      }
    },
  });

  return new Response(stream, {
    headers: {
      "content-type": "text/event-stream",
      "cache-control": "no-cache, no-transform",
      connection: "keep-alive",
    },
  });
}
