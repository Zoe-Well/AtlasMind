import { redirect } from "next/navigation";

import { EvaluationWorkbench } from "@/components/evaluations/evaluation-workbench";
import { AppShell } from "@/components/layout/app-shell";
import { serverSession } from "@/lib/auth/server-session";
import { publicSession } from "@/lib/auth/session";

export default async function EvaluationPage({ params }: { params: Promise<{ evaluationRunId: string }> }) {
  const session = await serverSession();
  if (!session) redirect("/login");
  const { evaluationRunId } = await params;
  return <AppShell session={publicSession(session)}><EvaluationWorkbench initialRunId={evaluationRunId} /></AppShell>;
}
