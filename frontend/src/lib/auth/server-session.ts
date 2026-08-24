import "server-only";

import { cookies } from "next/headers";

import { sessionSecret } from "./config";
import { readSessionToken, SESSION_COOKIE, type PrivateSession } from "./session";

export async function serverSession(): Promise<PrivateSession | null> {
  const store = await cookies();
  const token = store.get(SESSION_COOKIE)?.value;
  if (!token) {
    return null;
  }
  try {
    return await readSessionToken(token, sessionSecret());
  } catch {
    return null;
  }
}
