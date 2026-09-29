import { endpoint, getCsrfToken, handleUnauthorized } from "./api";
import { eventSchema, type DecisionEvent } from "./schemas";
export class SseParser {
  private pending = "";
  constructor(private readonly onEvent: (event: DecisionEvent) => void) {}
  push(chunk: string) {
    this.pending += chunk;
    this.consume();
  }
  private consume() {
    let match: RegExpExecArray | null;
    while ((match = /\r?\n\r?\n/.exec(this.pending)) !== null) {
      const frame = this.pending.slice(0, match.index);
      this.pending = this.pending.slice(match.index + match[0].length);
      const data = frame
        .split(/\r?\n/)
        .filter((line) => line.startsWith("data:"))
        .map((line) => line.slice(5).replace(/^ /, ""))
        .join("\n");
      if (data)
        this.onEvent(eventSchema.parse(JSON.parse(data)) as DecisionEvent);
    }
  }
  finish() {
    if (this.pending.trim())
      throw new Error("推荐进度数据不完整，请恢复查询结果");
  }
}
export async function stream(
  collectionPath: string,
  body: unknown,
  key: string,
  signal: AbortSignal,
  onEvent: (event: DecisionEvent) => void,
) {
  const creation = await fetch(endpoint(collectionPath), {
    method: "POST",
    signal,
    credentials: "include",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      "Idempotency-Key": key,
      "X-Request-ID": crypto.randomUUID(),
      "X-CSRF-Token": getCsrfToken() ?? "",
    },
    body: JSON.stringify(body),
  });
  const payload = await creation.json();
  if (!creation.ok || !payload.success) {
    if (creation.status === 401 && payload.error?.code === "AUTH_REQUIRED")
      handleUnauthorized();
    const error = payload;
    throw new Error(error.error?.message ?? "推荐请求失败");
  }
  const runId = payload.data?.decisionRunId;
  if (typeof runId !== "string") throw new Error("服务未返回决策记录");
  onEvent({
    type: "runStarted",
    requestId: creation.headers.get("X-Request-ID") ?? "",
    decisionRunId: runId,
  });

  const response = await fetch(endpoint(`/decision-runs/${runId}/events`), {
    method: "GET",
    signal,
    credentials: "include",
    headers: {
      Accept: "text/event-stream",
      "X-Request-ID": crypto.randomUUID(),
    },
  });
  if (!response.ok) {
    const error = await response.json();
    if (response.status === 401 && error.error?.code === "AUTH_REQUIRED")
      handleUnauthorized();
    throw new Error(error.error?.message ?? "推荐进度读取失败");
  }
  if (!response.body) throw new Error("浏览器不支持流式响应");
  const reader = response.body.getReader(),
    decoder = new TextDecoder();
  let terminal = false;
  const parser = new SseParser((e) => {
    if (["result", "runFailed", "confirmationRequired"].includes(e.type))
      terminal = true;
    onEvent(e);
  });
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      parser.push(decoder.decode(value, { stream: true }));
    }
    parser.push(decoder.decode());
    parser.finish();
    if (!terminal) throw new Error("连接已断开，可以恢复查询结果");
  } finally {
    reader.releaseLock();
  }
}
