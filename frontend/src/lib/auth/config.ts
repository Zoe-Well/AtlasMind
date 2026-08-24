import { z } from "zod";

const authModeSchema = z.enum(["local", "oidc"]);

export type AuthMode = z.infer<typeof authModeSchema>;

export function authMode(): AuthMode {
  return authModeSchema.parse(process.env.ATLASMIND_AUTH_MODE ?? "local");
}

export function sessionSecret(): string {
  const value = process.env.ATLASMIND_SESSION_SECRET;
  if (value && value.length >= 32) {
    return value;
  }
  if (process.env.NODE_ENV !== "production" && authMode() === "local") {
    return "atlasmind-local-session-secret-change-before-production";
  }
  throw new Error("ATLASMIND_SESSION_SECRET must contain at least 32 characters");
}

const oidcSchema = z.object({
  issuer: z.string().url(),
  clientId: z.string().min(1),
  clientSecret: z.string().min(1),
  authorizationEndpoint: z.string().url(),
  tokenEndpoint: z.string().url(),
  jwksUri: z.string().url(),
  redirectUri: z.string().url(),
});

export type OidcConfig = z.infer<typeof oidcSchema>;

export function oidcConfig(): OidcConfig {
  return oidcSchema.parse({
    issuer: process.env.ATLASMIND_OIDC_ISSUER,
    clientId: process.env.ATLASMIND_OIDC_CLIENT_ID,
    clientSecret: process.env.ATLASMIND_OIDC_CLIENT_SECRET,
    authorizationEndpoint: process.env.ATLASMIND_OIDC_AUTHORIZATION_ENDPOINT,
    tokenEndpoint: process.env.ATLASMIND_OIDC_TOKEN_ENDPOINT,
    jwksUri: process.env.ATLASMIND_OIDC_JWKS_URI,
    redirectUri: process.env.ATLASMIND_OIDC_REDIRECT_URI,
  });
}

export function backendApiUrl(): string | null {
  const value = process.env.ATLASMIND_API_URL?.replace(/\/$/, "");
  return value || null;
}
