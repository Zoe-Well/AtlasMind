import { redirect } from "next/navigation";

import { ChatShell } from "@/components/chat/chat-shell";
import { AppShell } from "@/components/layout/app-shell";
import { publicSession } from "@/lib/auth/session";
import { serverSession } from "@/lib/auth/server-session";

export default async function ChatPage() {
  const privateSession = await serverSession();
  if (!privateSession) redirect("/login");
  const session = publicSession(privateSession);

  return (
    <AppShell session={session}>
      <ChatShell mode={session.mode} />
    </AppShell>
  );
}
