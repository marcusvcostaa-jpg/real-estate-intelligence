// Shared by server actions and proxy.ts. Tokens issued by the FastAPI backend live only in
// httpOnly cookies; the browser never sees them and never calls the API directly.

export const API_URL = process.env.API_INTERNAL_URL ?? "http://localhost:8000/api/v1";

export const ACCESS_COOKIE = "rei_access";
export const REFRESH_COOKIE = "rei_refresh";

export type TokenPair = { access_token: string; refresh_token: string };

export function secondsUntilExpiry(jwt: string): number {
  const payload = JSON.parse(Buffer.from(jwt.split(".")[1], "base64url").toString());
  return Math.max(0, payload.exp - Math.floor(Date.now() / 1000));
}

export function cookieOptions(maxAge: number) {
  return {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax" as const,
    path: "/",
    maxAge,
  };
}
