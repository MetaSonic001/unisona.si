export const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
export const DEV_MODE_ENABLED = process.env.NEXT_PUBLIC_DEV_MODE === "true" && process.env.NODE_ENV !== "production";
export const CLERK_ENABLED = Boolean(process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY);
export const DEV_COOKIE = "unisona_dev";

export function isDevSession(): boolean {
  if (!DEV_MODE_ENABLED || typeof document === "undefined") return false;
  return document.cookie.split("; ").some((c) => c === `${DEV_COOKIE}=1`);
}

export function setDevSession(on: boolean) {
  document.cookie = on ? `${DEV_COOKIE}=1; path=/; max-age=2592000; samesite=lax` : `${DEV_COOKIE}=; path=/; max-age=0`;
}
