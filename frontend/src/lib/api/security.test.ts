import { describe, expect, it } from "vitest";

import { buildAgentRunPayload } from "./client";

describe("AgentRun public request boundary", () => {
  it("defaults to AUTO and only emits OpenAPI-approved fields", () => {
    const payload = buildAgentRunPayload({ query: "What is refund policy?" });
    expect(payload).toEqual({ query: "What is refund policy?", mode: "AUTO" });
    expect(payload).not.toHaveProperty("principal_id");
    expect(payload).not.toHaveProperty("role_codes");
    expect(payload).not.toHaveProperty("scope_ids");
    expect(payload).not.toHaveProperty("token");
  });

  it("rejects caller-supplied authority fields and unknown modes", () => {
    expect(() => buildAgentRunPayload({ query: "test", mode: "SIMPLE", scope: "secret" } as never)).toThrow();
    expect(() => buildAgentRunPayload({ query: "test", mode: "ADMIN" } as never)).toThrow();
  });
});
