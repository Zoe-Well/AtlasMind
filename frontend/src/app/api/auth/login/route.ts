import { NextResponse } from "next/server";

import { authMode, oidcConfig, sessionSecret } from "@/lib/auth/config";
import { pkceChallenge, randomUrlSafe } from "@/lib/auth/oidc";
import {
  createSessionToken,
  OIDC_TRANSACTION_COOKIE,
  SESSION_COOKIE,
} from "@/lib/auth/session";
import { createTransactionToken } from "@/lib/auth/transaction";

const cookieOptions = {
  httpOnly: true,
  secure: process.env.NODE_ENV === "production",
  sameSite: "lax" as const,
  path: "/",
};

export async function GET() {
  if (authMode() === "local") {
    const expiresAt = Math.floor(Date.now() / 1000) + 8 * 60 * 60;
    const token = await createSessionToken(
      {
        subject: "local-employee",
        displayName: "本地管理员",
        accessToken: "local-development-session",
        expiresAt,
        mode: "local",
      },
      sessionSecret(),
    );
    const response = new NextResponse(null, { status: 303, headers: { location: "/chat" } });
    response.cookies.set(SESSION_COOKIE, token, {
      ...cookieOptions,
      expires: new Date(expiresAt * 1000),
    });
    return response;
  }

  const config = oidcConfig();
  const transaction = {
    state: randomUrlSafe(),
    nonce: randomUrlSafe(),
    verifier: randomUrlSafe(48),
  };
  const transactionToken = await createTransactionToken(transaction, sessionSecret());
  const authorizationUrl = new URL(config.authorizationEndpoint);
  authorizationUrl.search = new URLSearchParams({
    response_type: "code",
    client_id: config.clientId,
    redirect_uri: config.redirectUri,
    scope: "openid profile email",
    state: transaction.state,
    nonce: transaction.nonce,
    code_challenge: pkceChallenge(transaction.verifier),
    code_challenge_method: "S256",
  }).toString();

  const response = NextResponse.redirect(authorizationUrl);
  response.cookies.set(OIDC_TRANSACTION_COOKIE, transactionToken, {
    ...cookieOptions,
    maxAge: 10 * 60,
  });
  return response;
}
