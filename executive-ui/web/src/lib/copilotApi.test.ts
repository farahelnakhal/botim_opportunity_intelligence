import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { copilotApi } from "./copilotApi";

describe("copilotApi (Phase 2B/2L)", () => {
  const realFetch = global.fetch;

  afterEach(() => {
    global.fetch = realFetch;
  });

  it("returns a normalized result on success", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        schema_version: "1.0", conversation_id: "conv_abc123456789", message_id: "msg_abc123456789",
        answer_markdown: "OPP-013 scores 55/85.", answer_type: "analysis",
        confidence: { level: "medium", basis: "test" },
        citations: [{ id: "OPP-013", type: "opportunity", title: "Import payment", role: "primary",
                     target: { type: "internal_route", value: "/opportunity/OPP-013" }, metadata: null }],
        assumptions: ["8 of 17 factors are assumption-based"],
        unknowns: [], recommended_next_actions: ["Run VE-004"], warnings: [], safe_tool_trace: [],
      }),
    }) as unknown as typeof fetch;

    const result = await copilotApi.chat("Explain OPP-013", null);
    expect(result.unavailable).toBe(false);
    expect(result.conversationId).toBe("conv_abc123456789");
    expect(result.citations).toHaveLength(1);
    expect(result.citations[0].id).toBe("OPP-013");
    expect(result.recommendedNextActions).toEqual(["Run VE-004"]);
  });

  it("returns an honest unavailable result on network failure — never throws, never fabricates", async () => {
    global.fetch = vi.fn().mockRejectedValue(new Error("network down")) as unknown as typeof fetch;
    const result = await copilotApi.chat("hello", null);
    expect(result.unavailable).toBe(true);
    expect(result.answerMarkdown).toBe("");
    expect(result.citations).toEqual([]);
  });

  it("returns an honest unavailable result on a non-2xx HTTP response", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false, status: 502,
      json: async () => ({ schema_version: "1.0", error: { code: "provider_error", message: "backend down" } }),
    }) as unknown as typeof fetch;
    const result = await copilotApi.chat("hello", null);
    expect(result.unavailable).toBe(true);
    expect(result.unavailableReason).toMatch(/backend down/);
  });

  it("returns an honest unavailable result on a malformed (non-JSON) body", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => { throw new Error("not json"); },
    }) as unknown as typeof fetch;
    const result = await copilotApi.chat("hello", null);
    expect(result.unavailable).toBe(true);
  });

  it("sends the conversation_id and context through unchanged for a follow-up", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        schema_version: "1.0", conversation_id: "conv_xyz", message_id: "msg_xyz",
        answer_markdown: "…", answer_type: "analysis", confidence: { level: "low", basis: "" },
        citations: [], assumptions: [], unknowns: [], recommended_next_actions: [], warnings: [],
        safe_tool_trace: [],
      }),
    });
    global.fetch = fetchMock as unknown as typeof fetch;
    await copilotApi.chat("follow-up", "conv_xyz", { opportunity_id: "OPP-013" });
    const [, init] = fetchMock.mock.calls[0];
    const body = JSON.parse(init.body as string);
    expect(body.conversation_id).toBe("conv_xyz");
    expect(body.context).toEqual({ opportunity_id: "OPP-013" });
  });
});
