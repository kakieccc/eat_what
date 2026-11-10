import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function returnPath(state: unknown): string {
  const from = state && typeof state === "object" && "from" in state ? state.from : null;
  return typeof from === "string" && from.startsWith("/") && !from.startsWith("//")
    && !/^\/(login|register|error)([/?#]|$)/.test(from) ? from : "/";
}

export function formatDistance(meters: number): string {
  return meters < 1000
    ? `${Math.round(meters)} 米`
    : `${Number((meters / 1000).toFixed(1))} km`;
}

export function formatBudget({ min, max }: { min: string | null; max: string | null }): string {
  if (min && max) return `人均 ¥${min}–${max}`;
  if (max) return `人均 ¥${max}以内`;
  if (min && Number(min) > 0) return `人均 ¥${min}起`;
  return "预算不限";
}

export function navigationHref(value: string | null | undefined): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    return url.protocol === "https:" && url.hostname === "uri.amap.com" ? url.href : null;
  } catch {
    return null;
  }
}
