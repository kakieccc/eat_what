import { z } from "zod";
const publicConfig = z.object({
  VITE_API_BASE_URL: z.url(),
  VITE_AMAP_JS_KEY: z
    .string()
    .min(1)
    .refine((v) => !v.startsWith("replace-")),
  VITE_AMAP_SECURITY_CODE: z
    .string()
    .min(1)
    .refine((v) => !v.startsWith("replace-")),
});
export const config = publicConfig.safeParse(import.meta.env);
export const configError = config.success
  ? null
  : "请先配置 src/frontend/.env 中的 API 地址、高德 JS Key 和安全码，然后重启前端。";
export const serverErrorMessage = "服务暂时不可用，请稍后重试";
let csrfToken: string | null = null;
let sessionVersion = 0;
export const getSessionVersion = () => sessionVersion;
export const advanceSession = () => ++sessionVersion;
export function requireCurrentSession(version: number, signal?: AbortSignal) {
  // A late response or 401 from an old account must not update the new account's state.
  if (version !== sessionVersion || signal?.aborted)
    throw new DOMException("Request is no longer current", "AbortError");
}
export function errorMessage(code: string, message?: string) {
  if (code === "QUEUE_TIMEOUT") return "本次请求排队超时，请稍后按当前条件重试。";
  if (code === "DECISION_TIMEOUT") return "本次推荐处理超时，请稍后按当前条件重试。";
  if (code === "INTERNAL_ERROR") return "服务器处理请求时出现异常，请稍后重试。";
  if (code === "LLM_UNAVAILABLE") return "推荐分析服务暂时不可用，请稍后按当前条件重试。";
  if (code === "LLM_INVALID_OUTPUT") return "推荐分析暂时没能生成有效结果，请按当前条件重试。";
  if (["AMAP_UNAVAILABLE", "AMAP_SCHEMA_ERROR", "AMAP_INVALID_RESPONSE"].includes(code))
    return "地图服务暂时异常，未能完成餐厅检索，请稍后重试。";
  if (code === "RUN_FAILED") return "本次推荐意外中断，请稍后按当前条件重试。";
  if (code === "PREFERENCE_CONFLICT") return "偏好已更新，请刷新页面后再保存";
  if (code === "SELECTION_COMPLETED")
    return "本次选餐已结束，请开始新的选餐。";
  if (code === "WORKFLOW_UPGRADED")
    return "选餐流程已更新，请开始新的选餐。";
  if (["RUN_SUPERSEDED", "INVALID_STATE", "IDEMPOTENCY_CONFLICT"].includes(code))
    return "当前推荐状态已变化，请刷新后重试。";
  return message ?? "服务暂时不可用";
}
let unauthorizedHandler: (() => void) | null = null;
let serviceErrorHandler: (() => void) | null = null;

export function setServiceErrorHandler(handler: (() => void) | null) {
  serviceErrorHandler = handler;
}

export function setCsrfToken(value: string | null) {
  csrfToken = value;
}
export function setUnauthorizedHandler(handler: (() => void) | null) {
  unauthorizedHandler = handler;
}
export function handleUnauthorized() {
  unauthorizedHandler?.();
}
export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public code: string,
    public retryable = false,
    public requestId: string | null = null,
  ) {
    super(message);
  }
}
export function endpoint(path: string) {
  if (!config.success) throw new Error(configError ?? "配置不完整");
  return config.data.VITE_API_BASE_URL.replace(/\/$/, "") + path;
}
export async function fetchResponse(path: string, options: RequestInit): Promise<Response> {
  const version = getSessionVersion();
  const signal = options.signal ?? undefined;
  let response: Response;
  try {
    response = await fetch(endpoint(path), { ...options, credentials: "include" });
  } catch (error) {
    requireCurrentSession(version, signal);
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    serviceErrorHandler?.();
    throw new Error(configError ?? serverErrorMessage);
  }
  requireCurrentSession(version, signal);
  return response;
}

const successEnvelopeSchema = z.object({
  success: z.literal(true),
  data: z.unknown(),
});
const errorEnvelopeSchema = z.object({
  success: z.literal(false),
  error: z.object({
    code: z.string(),
    message: z.string(),
    details: z.object({ retryable: z.boolean().optional() }).optional(),
  }),
  meta: z.object({ requestId: z.string().optional() }).optional(),
});

export async function responseData(response: Response, signal?: AbortSignal): Promise<unknown> {
  const version = getSessionVersion();
  const payload = await response.json().catch((error: unknown) => {
    requireCurrentSession(version, signal);
    if (response.ok) throw error;
    return null;
  });
  requireCurrentSession(version, signal);
  const result = successEnvelopeSchema.safeParse(payload);
  if (!response.ok || !result.success) {
    const parsed = errorEnvelopeSchema.safeParse(payload);
    const envelope = parsed.success ? parsed.data : null;
    const code = envelope?.error.code ?? (response.status >= 500 ? "INTERNAL_ERROR" : "UNKNOWN");
    if (response.status === 401 && code === "AUTH_REQUIRED") handleUnauthorized();
    if (response.status >= 500 && !["QUEUE_FULL", "AUTH_BUSY", "STREAM_CAPACITY_REACHED"].includes(code))
      serviceErrorHandler?.();
    throw new ApiError(
      errorMessage(code, envelope?.error.message ?? serverErrorMessage),
      response.status,
      code,
      envelope?.error.details?.retryable ?? false,
      envelope?.meta?.requestId ?? response.headers.get("X-Request-ID"),
    );
  }
  return result.data.data;
}
export async function request<T>(
  path: string,
  body?: unknown,
  method = body === undefined ? "GET" : "POST",
  key?: string,
  signal?: AbortSignal,
  schema?: z.ZodType<T>,
): Promise<T> {
  const version = getSessionVersion();
  const response = await fetchResponse(path, {
    method,
    signal,
    headers: {
      "Content-Type": "application/json",
      "X-Request-ID": crypto.randomUUID(),
      ...(path === "/auth/login" || path === "/auth/register"
        ? { "X-Auth-Intent": "web" }
        : {}),
      ...(body !== undefined && csrfToken
        ? { "X-CSRF-Token": csrfToken }
        : {}),
      ...(body !== undefined
        ? { "Idempotency-Key": key ?? crypto.randomUUID() }
        : {}),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await responseData(response, signal);
  requireCurrentSession(version, signal);
  return schema ? schema.parse(data) : (data as T);
}
