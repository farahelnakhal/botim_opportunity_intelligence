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

  const notFoundResponse = {
    ok: false, status: 404,
    json: async () => ({ schema_version: "1.0", error: { code: "conversation_not_found", message: "the conversation no longer exists" } }),
  };
  const successResponse = (conversationId: string) => ({
    ok: true,
    json: async () => ({
      schema_version: "1.0", conversation_id: conversationId, message_id: "msg_new",
      answer_markdown: "fresh answer", answer_type: "analysis", confidence: { level: "low", basis: "" },
      citations: [], assumptions: [], unknowns: [], recommended_next_actions: [], warnings: [],
      safe_tool_trace: [],
    }),
  });

  describe("stale-conversation recovery (Phase 3)", () => {
    it("retries exactly once with conversation_id: null after conversation_not_found, preserving message/context", async () => {
      const fetchMock = vi.fn()
        .mockResolvedValueOnce(notFoundResponse)
        .mockResolvedValueOnce(successResponse("conv_new123456789"));
      global.fetch = fetchMock as unknown as typeof fetch;

      const result = await copilotApi.chat("what are the risks?", "conv_stale000000000", { opportunity_id: "OPP-010" });

      expect(fetchMock).toHaveBeenCalledTimes(2);
      const firstBody = JSON.parse(fetchMock.mock.calls[0][1].body as string);
      const secondBody = JSON.parse(fetchMock.mock.calls[1][1].body as string);
      expect(firstBody.conversation_id).toBe("conv_stale000000000");
      expect(secondBody.conversation_id).toBeNull();
      expect(secondBody.message).toBe("what are the risks?");
      expect(secondBody.context).toEqual({ opportunity_id: "OPP-010" });

      expect(result.unavailable).toBe(false);
      expect(result.conversationId).toBe("conv_new123456789");
      expect(result.staleConversationRecovered).toBe(true);
    });

    it("never retries more than once — a second conversation_not_found still ends in unavailable", async () => {
      const fetchMock = vi.fn()
        .mockResolvedValueOnce(notFoundResponse)
        .mockResolvedValueOnce(notFoundResponse);
      global.fetch = fetchMock as unknown as typeof fetch;

      const result = await copilotApi.chat("hi", "conv_stale", {});
      expect(fetchMock).toHaveBeenCalledTimes(2);
      expect(result.unavailable).toBe(true);
    });

    it("does not retry when no conversation_id was sent in the first place", async () => {
      const fetchMock = vi.fn().mockResolvedValueOnce(notFoundResponse);
      global.fetch = fetchMock as unknown as typeof fetch;

      const result = await copilotApi.chat("hi", null, {});
      expect(fetchMock).toHaveBeenCalledTimes(1);
      expect(result.unavailable).toBe(true);
    });

    it("does not retry for a plain 500 error", async () => {
      const fetchMock = vi.fn().mockResolvedValueOnce({
        ok: false, status: 500,
        json: async () => ({ schema_version: "1.0", error: { code: "internal", message: "boom" } }),
      });
      global.fetch = fetchMock as unknown as typeof fetch;
      const result = await copilotApi.chat("hi", "conv_x", {});
      expect(fetchMock).toHaveBeenCalledTimes(1);
      expect(result.unavailable).toBe(true);
    });

    it("does not retry for a timeout/network failure", async () => {
      const fetchMock = vi.fn().mockRejectedValueOnce(new Error("network down"));
      global.fetch = fetchMock as unknown as typeof fetch;
      const result = await copilotApi.chat("hi", "conv_x", {});
      expect(fetchMock).toHaveBeenCalledTimes(1);
      expect(result.unavailable).toBe(true);
    });

    it("does not retry for a malformed (non-JSON) response", async () => {
      const fetchMock = vi.fn().mockResolvedValueOnce({
        ok: false, status: 404,
        json: async () => { throw new Error("not json"); },
      });
      global.fetch = fetchMock as unknown as typeof fetch;
      const result = await copilotApi.chat("hi", "conv_x", {});
      expect(fetchMock).toHaveBeenCalledTimes(1);
      expect(result.unavailable).toBe(true);
    });

    it("does not retry for an authentication failure", async () => {
      const fetchMock = vi.fn().mockResolvedValueOnce({
        ok: false, status: 401,
        json: async () => ({ schema_version: "1.0", error: { code: "unauthorized", message: "nope" } }),
      });
      global.fetch = fetchMock as unknown as typeof fetch;
      const result = await copilotApi.chat("hi", "conv_x", {});
      expect(fetchMock).toHaveBeenCalledTimes(1);
      expect(result.unavailable).toBe(true);
    });
  });

  describe("runtime_mode passthrough (Phase 3)", () => {
    it("parses a valid runtime_mode", async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          schema_version: "1.0", conversation_id: "conv_a", message_id: "msg_a",
          answer_markdown: "x", answer_type: "analysis", confidence: { level: "low", basis: "" },
          citations: [], assumptions: [], unknowns: [], recommended_next_actions: [], warnings: [],
          safe_tool_trace: [], runtime_mode: "deterministic_demo",
        }),
      }) as unknown as typeof fetch;
      const result = await copilotApi.chat("hi", null);
      expect(result.runtimeMode).toBe("deterministic_demo");
    });

    it("is safe (undefined) when runtime_mode is absent — backward compatible", async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          schema_version: "1.0", conversation_id: "conv_a", message_id: "msg_a",
          answer_markdown: "x", answer_type: "analysis", confidence: { level: "low", basis: "" },
          citations: [], assumptions: [], unknowns: [], recommended_next_actions: [], warnings: [],
          safe_tool_trace: [],
        }),
      }) as unknown as typeof fetch;
      const result = await copilotApi.chat("hi", null);
      expect(result.runtimeMode).toBeUndefined();
    });

    it("is safe (undefined) for an unrecognized runtime_mode value", async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          schema_version: "1.0", conversation_id: "conv_a", message_id: "msg_a",
          answer_markdown: "x", answer_type: "analysis", confidence: { level: "low", basis: "" },
          citations: [], assumptions: [], unknowns: [], recommended_next_actions: [], warnings: [],
          safe_tool_trace: [], runtime_mode: "something_new_future_value",
        }),
      }) as unknown as typeof fetch;
      const result = await copilotApi.chat("hi", null);
      expect(result.runtimeMode).toBeUndefined();
    });
  });
});
