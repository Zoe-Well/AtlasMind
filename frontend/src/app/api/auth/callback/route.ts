import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { oidcConfig, sessionSecret } from "@/lib/auth/config";
import { exchangeAuthorizationCode } from "@/lib/auth/oidc";
import {
  createSessionToken,
  OIDC_TRANSACTION_COOKIE,
  SESSION_COOKIE,
} from "@/lib/auth/session";
import { readTransactionToken } from "@/lib/auth/transaction";

function localRedirect(location: string) {
  const response = new NextResponse(null, { status: 303, headers: { location } });
  response.cookies.delete(OIDC_TRANSACTION_COOKIE);
  return response;
}

export async function GET(request: Request) {
  const url = new URL(request.url);
  const code = url.searchParams.get("code");
  const state = url.searchParams.get("state");
  const store = await cookies();
  const transactionToken = store.get(OIDC_TRANSACTION_COOKIE)?.value;

  if (!code || !state || !transactionToken) {
    return localRedirect("/login?error=oidc_callback_invalid");
  }

  try {
    const transaction = await readTransactionToken(transactionToken, sessionSecret());
    if (transaction.state !== state) throw new Error("OIDC state mismatch");

    const identity = await exchangeAuthorizationCode(
      code,
      transaction.verifier,
      transaction.nonce,
      oidcConfig(),
    );
    const sessionToken = await createSessionToken(
      { ...identity, mode: "oidc" },
      sessionSecret(),
    );
    const response = localRedirect("/chat");
    response.cookies.set(SESSION_COOKIE, sessionToken, {
      httpOnly: true,
      secure: process.env.NODE_ENV === "production",
      sameSite: "lax",
      path: "/",
      expires: new Date(identity.expiresAt * 1000),
    });
    return response;
  } catch {
    return localRedirect("/login?error=oidc_verification_failed");
  }
}
