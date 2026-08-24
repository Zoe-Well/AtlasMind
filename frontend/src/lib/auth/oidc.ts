import { createHash, randomBytes } from "node:crypto";

import { createRemoteJWKSet, decodeJwt, jwtVerify } from "jose";

import type { OidcConfig } from "./config";

export function randomUrlSafe(bytes = 32): string {
  return randomBytes(bytes).toString("base64url");
}

export function pkceChallenge(verifier: string): string {
  return createHash("sha256").update(verifier).digest("base64url");
}

export async function exchangeAuthorizationCode(
  code: string,
  verifier: string,
  nonce: string,
  config: OidcConfig,
): Promise<{ subject: string; displayName: string; email?: string; accessToken: string; expiresAt: number }> {
  const body = new URLSearchParams({
    grant_type: "authorization_code",
    code,
    redirect_uri: config.redirectUri,
    client_id: config.clientId,
    client_secret: config.clientSecret,
    code_verifier: verifier,
  });
  const response = await fetch(config.tokenEndpoint, {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body,
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error("OIDC token exchange failed");
  }
  const tokens = (await response.json()) as {
    access_token?: string;
    id_token?: string;
    expires_in?: number;
  };
  if (!tokens.access_token || !tokens.id_token) {
    throw new Error("OIDC response is missing required tokens");
  }
  const unverified = decodeJwt(tokens.id_token);
  if (unverified.nonce !== nonce) {
    throw new Error("OIDC nonce mismatch");
  }
  const { payload } = await jwtVerify(tokens.id_token, createRemoteJWKSet(new URL(config.jwksUri)), {
    issuer: config.issuer,
    audience: config.clientId,
  });
  if (!payload.sub) {
    throw new Error("OIDC subject is missing");
  }
  return {
    subject: payload.sub,
    displayName: typeof payload.name === "string" ? payload.name : "Enterprise employee",
    ...(typeof payload.email === "string" ? { email: payload.email } : {}),
    accessToken: tokens.access_token,
    expiresAt: Math.min(
      typeof payload.exp === "number" ? payload.exp : Number.MAX_SAFE_INTEGER,
      Math.floor(Date.now() / 1000) + (tokens.expires_in ?? 300),
    ),
  };
}
