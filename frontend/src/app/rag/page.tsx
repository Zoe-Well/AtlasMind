import { redirect } from "next/navigation";
import { AppShell } from "@/components/layout/app-shell";
import { RagStrategyWorkbench } from "@/components/rag/rag-strategy-workbench";
import { publicSession } from "@/lib/auth/session";
import { serverSession } from "@/lib/auth/server-session";
export default async function RagPage(){const session=await serverSession();if(!session)redirect("/login");return <AppShell session={publicSession(session)}><RagStrategyWorkbench/></AppShell>;}
