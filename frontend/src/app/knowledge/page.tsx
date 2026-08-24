import { redirect } from "next/navigation";

import { KnowledgeWorkbench } from "@/components/knowledge/knowledge-workbench";
import { AppShell } from "@/components/layout/app-shell";
import { serverSession } from "@/lib/auth/server-session";
import { publicSession } from "@/lib/auth/session";

export default async function KnowledgePage() {
  const privateSession = await serverSession();
  if (!privateSession) redirect("/login");
  return <AppShell session={publicSession(privateSession)}><KnowledgeWorkbench /></AppShell>;
}
