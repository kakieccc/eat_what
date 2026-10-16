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
let csrfToken: string | null = null;
let sessionVersion = 0;
export const getSessionVersion = () => sessionVersion;
export const advanceSession = () => ++sessionVersion;
export function requireCurrentSession(version: number, signal?: AbortSignal) {
  if (version !== sessionVersion || signal?.aborted)
    throw new DOMException("Request is no longer current", "AbortError");
}
export function errorMessage(code: string, message?: string) {
  if (code === "ALLERGY_REQUIREMENT_UNVERIFIABLE")
    return "当前餐厅数据无法核实配料及交叉接触情况，无法按过敏要求推荐，请直接向餐厅确认。";
  if (["RUN_SUPERSEDED", "INVALID_STATE", "IDEMPOTENCY_CONFLICT"].includes(code))
    return "当前推荐状态已变化，请刷新后重试。";
  return code === "INPUT_CONFLICT"
    ? "表单条件与补充说明存在冲突，请调整条件后重试。"
    : (message ?? "服务暂时不可用");
}
let unauthorizedHandler: (() => void) | null = null;

export function setCsrfToken(value: string | null) {
  csrfToken = value;
}
export function getCsrfToken() {
  return csrfToken;
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
export async function request<T>(
  path: string,
  body?: unknown,
  method = body === undefined ? "GET" : "POST",
  key?: string,
  signal?: AbortSignal,
  schema?: z.ZodType<T>,
): Promise<T> {
  const version = getSessionVersion();
  let response: Response;
  try {
    response = await fetch(endpoint(path), {
      method,
      signal,
      credentials: "include",
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
  } catch (e) {
    requireCurrentSession(version, signal);
    if (e instanceof DOMException && e.name === "AbortError") throw e;
    throw new Error(configError ?? "连接失败，请确认本地后端已启动");
  }
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
