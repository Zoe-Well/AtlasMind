import { redirect } from "next/navigation";
import { GovernanceWorkbench } from "@/components/governance/governance-workbench";
import { AppShell } from "@/components/layout/app-shell";
import { publicSession } from "@/lib/auth/session";
import { serverSession } from "@/lib/auth/server-session";
export default async function GovernancePage(){const session=await serverSession();if(!session)redirect("/login");return <AppShell session={publicSession(session)}><GovernanceWorkbench/></AppShell>;}
