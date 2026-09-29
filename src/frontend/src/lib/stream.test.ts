import { afterEach, describe, it, expect, vi } from "vitest";
import { SseParser, stream } from "./stream";
import type { DecisionEvent } from "./schemas";

vi.mock("./api", () => ({
  endpoint: (path: string) => `https://api.test${path}`,
  getCsrfToken: () => "test-csrf",
  handleUnauthorized: vi.fn(),
}));

afterEach(() => vi.unstubAllGlobals());

describe("SSE frames", () => {
  it("supports split CRLF and multiple frames", () => {
    const events: DecisionEvent[] = [];
    const parser = new SseParser((e) => events.push(e));
    const a = 'data: {"type":"heartbeat","timestamp":"2026-09-07"}\r\n\r\n';
    for (const char of a + a) parser.push(char);
    parser.finish();
    expect(events).toHaveLength(2);
  });
  it("ignores comments and rejects unknown business events", () => {
    const parser = new SseParser(() => {});
    parser.push(": keep alive\n\n");
    expect(() => parser.push('data: {"type":"thought"}\n\n')).toThrow();
  });
  it("rejects truncated frames", () => {
    const parser = new SseParser(() => {});
    parser.push("data: {");
    expect(() => parser.finish()).toThrow();
  });
});

describe("decision event resource", () => {
  it("creates a run before subscribing to its event resource", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            success: true,
            data: { decisionRunId: "run-1" },
          }),
          {
            status: 201,
            headers: {
              "Content-Type": "application/json",
              "X-Request-ID": "request-1",
            },
          },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          'data: {"type":"runFailed","error":{"code":"FAILED","message":"failed"}}\n\n',
          { status: 200, headers: { "Content-Type": "text/event-stream" } },
        ),
      );
    vi.stubGlobal("fetch", fetchMock);
    const events: DecisionEvent[] = [];

    await stream(
      "/decision-runs",
      { origin: {} },
      "idempotency-key",
      new AbortController().signal,
      (event) => events.push(event),
    );

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "https://api.test/decision-runs",
      expect.objectContaining({ method: "POST" }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "https://api.test/decision-runs/run-1/events",
      expect.objectContaining({ method: "GET" }),
    );
    expect(events.map((event) => event.type)).toEqual([
      "runStarted",
      "runFailed",
    ]);
  });
});
