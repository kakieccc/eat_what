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
export const serverErrorMessage = "500 Error：服务暂时不可用";
let csrfToken: string | null = null;
let sessionVersion = 0;
export const getSessionVersion = () => sessionVersion;
export const advanceSession = () => ++sessionVersion;
export function requireCurrentSession(version: number, signal?: AbortSignal) {
  if (version !== sessionVersion || signal?.aborted)
    throw new DOMException("Request is no longer current", "AbortError");
}
export function errorMessage(code: string, message?: string) {
  if (code === "QUEUE_TIMEOUT") return "排队超过等待时限，请重新推荐。";
  if (code === "PREFERENCE_CONFLICT") return "偏好已更新，请点击重新读取偏好后再修改保存";
  if (code === "SELECTION_COMPLETED")
    return "本次选餐已结束，请开始新的选餐。";
  if (code === "WORKFLOW_UPGRADED")
    return "选餐流程已更新，请开始新的选餐。";
  if (["RUN_SUPERSEDED", "INVALID_STATE", "IDEMPOTENCY_CONFLICT"].includes(code))
    return "当前推荐状态已变化，请刷新后重试。";
  return message ?? "服务暂时不可用";
}
let unauthorizedHandler: (() => void) | null = null;

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
    throw new Error(configError ?? serverErrorMessage);
  }
  requireCurrentSession(version, signal);
  if (response.status >= 500)
    throw new ApiError(serverErrorMessage, response.status, "INTERNAL_ERROR");
  return response;
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
  const payload = await response.json();
  requireCurrentSession(version, signal);
  if (!response.ok || !payload.success) {
    if (response.status === 401 && payload.error?.code === "AUTH_REQUIRED")
      handleUnauthorized();
    const code = payload.error?.code ?? "UNKNOWN";
    const message = errorMessage(code, payload.error?.message);
    throw new ApiError(message, response.status, code);
  }
  return schema ? schema.parse(payload.data) : (payload.data as T);
}
