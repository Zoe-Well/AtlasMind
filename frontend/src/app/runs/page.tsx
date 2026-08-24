import { redirect } from "next/navigation";
import { AppShell } from "@/components/layout/app-shell";
import { RunCenter } from "@/components/runs/run-center";
import { publicSession } from "@/lib/auth/session";
import { serverSession } from "@/lib/auth/server-session";
export default async function RunsPage(){const session=await serverSession();if(!session)redirect("/login");return <AppShell session={publicSession(session)}><RunCenter/></AppShell>;}
