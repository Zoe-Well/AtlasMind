import { createHash } from "node:crypto";

import { EncryptJWT, jwtDecrypt } from "jose";
import { z } from "zod";

const transactionSchema = z.object({
  state: z.string().min(16),
  nonce: z.string().min(16),
  verifier: z.string().min(32),
});

export type OidcTransaction = z.infer<typeof transactionSchema>;

function key(secret: string): Uint8Array {
  return new Uint8Array(createHash("sha256").update(secret).digest());
}

export async function createTransactionToken(
  transaction: OidcTransaction,
  secret: string,
): Promise<string> {
  return new EncryptJWT(transactionSchema.parse(transaction))
    .setProtectedHeader({ alg: "dir", enc: "A256GCM" })
    .setIssuedAt()
    .setExpirationTime("10m")
    .encrypt(key(secret));
}

export async function readTransactionToken(
  token: string,
  secret: string,
): Promise<OidcTransaction> {
  const { payload } = await jwtDecrypt(token, key(secret));
  return transactionSchema.parse(payload);
}
