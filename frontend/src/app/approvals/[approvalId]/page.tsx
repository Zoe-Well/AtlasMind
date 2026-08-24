import { redirect } from "next/navigation";

import { ApprovalWorkbench } from "@/components/approvals/approval-workbench";
import { AppShell } from "@/components/layout/app-shell";
import { serverSession } from "@/lib/auth/server-session";
import { publicSession } from "@/lib/auth/session";

export default async function ApprovalPage({ params }: { params: Promise<{ approvalId: string }> }) {
  const session = await serverSession();
  if (!session) redirect("/login");
  const { approvalId } = await params;
  return <AppShell session={publicSession(session)}><ApprovalWorkbench initialApprovalId={approvalId} /></AppShell>;
}
