import { createHash } from "node:crypto";

import { EncryptJWT, jwtDecrypt } from "jose";
import { z } from "zod";

export const SESSION_COOKIE = "atlasmind_session";
export const OIDC_TRANSACTION_COOKIE = "atlasmind_oidc_transaction";

const privateSessionSchema = z.object({
  subject: z.string().min(1),
  displayName: z.string().min(1),
  email: z.string().email().optional(),
  accessToken: z.string().optional(),
  expiresAt: z.number().int().positive(),
  mode: z.enum(["local", "oidc"]),
});

export type PrivateSession = z.infer<typeof privateSessionSchema>;

export interface PublicSession {
  authenticated: true;
  displayName: string;
  email?: string;
  mode: "local" | "oidc";
}

function encryptionKey(secret: string): Uint8Array {
  if (secret.length < 32) {
    throw new Error("Session secret must contain at least 32 characters");
  }
  return new Uint8Array(createHash("sha256").update(secret).digest());
}

export async function createSessionToken(session: PrivateSession, secret: string): Promise<string> {
  const value = privateSessionSchema.parse(session);
  return new EncryptJWT({ ...value })
    .setProtectedHeader({ alg: "dir", enc: "A256GCM" })
    .setIssuedAt()
    .setExpirationTime(value.expiresAt)
    .encrypt(encryptionKey(secret));
}

export async function readSessionToken(token: string, secret: string): Promise<PrivateSession> {
  const { payload } = await jwtDecrypt(token, encryptionKey(secret));
  return privateSessionSchema.parse(payload);
}

export function publicSession(session: PrivateSession): PublicSession {
  return {
    authenticated: true,
    displayName: session.displayName,
    ...(session.email ? { email: session.email } : {}),
    mode: session.mode,
  };
}
