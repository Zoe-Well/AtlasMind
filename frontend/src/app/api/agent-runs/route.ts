import { backendFetch } from "@/lib/api/server";
import { serverSession } from "@/lib/auth/server-session";
import { buildAgentRunPayload } from "@/lib/api/client";

export async function POST(request: Request) {
  const session = await serverSession();
  if (!session) {
    return Response.json({ code: "UNAUTHENTICATED" }, { status: 401 });
  }
  try {
    const payload = buildAgentRunPayload(await request.json());
    return backendFetch(session, "/v1/agent-runs", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch {
    return Response.json({ code: "INVALID_REQUEST" }, { status: 400 });
  }
}
