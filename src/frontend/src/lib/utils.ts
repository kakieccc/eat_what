import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatDistance(meters: number): string {
  return meters < 1000
    ? `${Math.round(meters)} 米`
    : `${Number((meters / 1000).toFixed(1))} km`;
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
