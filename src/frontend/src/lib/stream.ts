import { ApiError, endpoint, getCsrfToken, handleUnauthorized, errorMessage, getSessionVersion, requireCurrentSession } from "./api";
import { runSchema, eventSchema, type DecisionEvent, type Run } from "./schemas";
export class SseParser {
  private pending = "";
  constructor(private readonly onEvent: (event: DecisionEvent) => void | boolean) {}
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
      if (data && this.onEvent(eventSchema.parse(JSON.parse(data)) as DecisionEvent) === false) {
        this.pending = "";
        return;
      }
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
  onAccepted?: (run: Run) => void,
) {
  const version = getSessionVersion();
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
  requireCurrentSession(version, signal);
  if (!creation.ok || !payload.success) {
    if (creation.status === 401 && payload.error?.code === "AUTH_REQUIRED")
      handleUnauthorized();
    throw new ApiError(errorMessage(payload.error?.code, payload.error?.message), creation.status, payload.error?.code);
  }
  const runId = payload.data?.decisionRunId;
  if (typeof runId !== "string") throw new Error("服务未返回决策记录");
  if (onAccepted) onAccepted(runSchema.parse(payload.data));
  onEvent({
    type: "runStarted",
    requestId: creation.headers.get("X-Request-ID") ?? "",
    decisionRunId: runId,
  });

  await subscribe(runId, signal, onEvent);
}

export async function subscribe(
  runId: string,
  signal: AbortSignal,
  onEvent: (event: DecisionEvent) => void,
) {
  const version = getSessionVersion();
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
    requireCurrentSession(version, signal);
    if (response.status === 401 && error.error?.code === "AUTH_REQUIRED")
      handleUnauthorized();
    throw new ApiError(errorMessage(error.error?.code, error.error?.message), response.status, error.error?.code);
  }
  if (!response.body) throw new Error("浏览器不支持流式响应");
  const reader = response.body.getReader(),
    decoder = new TextDecoder();
  let terminal = false;
  const cancel = () => { void reader.cancel().catch(() => undefined); };
  signal.addEventListener("abort", cancel, { once: true });
  const parser = new SseParser((e) => {
    requireCurrentSession(version, signal);
    if (terminal) return false;
    if (["result", "runFailed"].includes(e.type)) terminal = true;
    onEvent(e);
    return !terminal;
  });
  try {
    while (true) {
      requireCurrentSession(version, signal);
      const { done, value } = await reader.read();
      requireCurrentSession(version, signal);
      if (done) break;
      parser.push(decoder.decode(value, { stream: true }));
      if (terminal) return;
    }
    parser.push(decoder.decode());
    parser.finish();
    if (!terminal) throw new Error("连接已断开，可以恢复查询结果");
  } finally {
    signal.removeEventListener("abort", cancel);
    await reader.cancel().catch(() => undefined);
    reader.releaseLock();
  }
}
