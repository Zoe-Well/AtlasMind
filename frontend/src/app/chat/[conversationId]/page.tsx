import { notFound, redirect } from "next/navigation";
import { z } from "zod";

import { ChatShell } from "@/components/chat/chat-shell";
import { AppShell } from "@/components/layout/app-shell";
import { publicSession } from "@/lib/auth/session";
import { serverSession } from "@/lib/auth/server-session";

export default async function ConversationPage({params}:{params:Promise<{conversationId:string}>}) {
  const privateSession=await serverSession();
  if(!privateSession)redirect("/login");
  const {conversationId}=await params;
  if(!z.string().uuid().safeParse(conversationId).success)notFound();
  const session=publicSession(privateSession);
  return <AppShell session={session}>
    <ChatShell key={conversationId} mode={session.mode} conversationId={conversationId}/>
  </AppShell>;
}
