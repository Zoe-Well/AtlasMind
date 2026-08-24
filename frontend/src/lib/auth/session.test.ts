import { describe, expect, it } from "vitest";

import { createSessionToken, publicSession, readSessionToken } from "./session";

describe("server-owned BFF session", () => {
  it("encrypts tokens and only exposes safe identity fields", async () => {
    const token = await createSessionToken(
      {
        subject: "employee-001",
        displayName: "Local Employee",
        email: "employee@example.invalid",
        accessToken: "server-only-access-token",
        expiresAt: Math.floor(Date.now() / 1000) + 300,
        mode: "oidc",
      },
      "test-secret-at-least-thirty-two-characters",
    );

    expect(token).not.toContain("server-only-access-token");
    const session = await readSessionToken(token, "test-secret-at-least-thirty-two-characters");
    expect(publicSession(session)).toEqual({
      authenticated: true,
      displayName: "Local Employee",
      email: "employee@example.invalid",
      mode: "oidc",
    });
  });

  it("does not use browser storage as an authority source", () => {
    expect(localStorage).toHaveLength(0);
  });
});
