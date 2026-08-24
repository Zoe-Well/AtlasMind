import { NextResponse } from "next/server";

import { OIDC_TRANSACTION_COOKIE, SESSION_COOKIE } from "@/lib/auth/session";

export async function POST() {
  const response = new NextResponse(null, { status: 303, headers: { location: "/login" } });
  response.cookies.delete(SESSION_COOKIE);
  response.cookies.delete(OIDC_TRANSACTION_COOKIE);
  return response;
}
