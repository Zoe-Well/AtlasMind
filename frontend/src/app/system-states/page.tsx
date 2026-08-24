import { redirect } from "next/navigation";
import { AppShell } from "@/components/layout/app-shell";
import { SystemStates } from "@/components/system/system-states";
import { publicSession } from "@/lib/auth/session";
import { serverSession } from "@/lib/auth/server-session";
export default async function SystemStatesPage(){const session=await serverSession();if(!session)redirect("/login");return <AppShell session={publicSession(session)}><SystemStates/></AppShell>;}
