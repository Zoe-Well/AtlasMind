import { redirect } from "next/navigation";

import { AppShell } from "@/components/layout/app-shell";
import { RunInspector } from "@/components/runs/run-inspector";
import { publicSession } from "@/lib/auth/session";
import { serverSession } from "@/lib/auth/server-session";

export default async function RunPage({ params }: { params: Promise<{ runId: string }> }) {
  const privateSession = await serverSession();
  if (!privateSession) redirect("/login");
  const { runId } = await params;

  return (
    <AppShell session={publicSession(privateSession)}>
      <RunInspector runId={runId} />
    </AppShell>
  );
}
