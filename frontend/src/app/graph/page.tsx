import { redirect } from "next/navigation";

import { GraphGovernance } from "@/components/graph/graph-governance";
import { AppShell } from "@/components/layout/app-shell";
import { serverSession } from "@/lib/auth/server-session";
import { publicSession } from "@/lib/auth/session";

export default async function GraphPage() {
  const session = await serverSession();
  if (!session) redirect("/login");
  return <AppShell session={publicSession(session)}><GraphGovernance /></AppShell>;
}
