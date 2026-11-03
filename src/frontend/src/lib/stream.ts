import { fetchResponse, handleUnauthorized, responseData, getSessionVersion, requireCurrentSession } from "./api";
import { eventSchema, type DecisionEvent } from "./schemas";
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
      if (data && this.onEvent(eventSchema.parse(JSON.parse(data))) === false) {
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
export async function subscribe(
  runId: string,
  signal: AbortSignal,
  onEvent: (event: DecisionEvent) => void,
) {
  const version = getSessionVersion();
  const response = await fetchResponse(`/decision-runs/${runId}/events`, {
    method: "GET",
    signal,
    headers: {
      Accept: "text/event-stream",
      "X-Request-ID": crypto.randomUUID(),
    },
  });
  if (!response.ok) {
    await responseData(response, signal);
  }
  if (!response.body) throw new Error("浏览器不支持流式响应");
  const reader = response.body.getReader(),
    decoder = new TextDecoder();
  let terminal = false;
  const cancel = () => reader.cancel().catch((error: unknown) => {
    console.error("Unable to close the recommendation stream", error);
  });
  const abort = () => { void cancel(); };
  signal.addEventListener("abort", abort, { once: true });
  const parser = new SseParser((e) => {
    requireCurrentSession(version, signal);
    if (terminal) return false;
    if (e.type === "runFailed" && e.error.code === "AUTH_REQUIRED") {
      handleUnauthorized();
      requireCurrentSession(version, signal);
    }
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
    signal.removeEventListener("abort", abort);
    // Terminal events also close HTTP so the server can release its limited SSE slot.
    await cancel();
    reader.releaseLock();
  }
}
