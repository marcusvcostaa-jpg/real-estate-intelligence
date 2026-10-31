import "server-only";
import { cookies } from "next/headers";
import { ACCESS_COOKIE, REFRESH_COOKIE, cookieOptions, secondsUntilExpiry, type TokenPair } from "./tokens";

export async function storeTokens(tokens: TokenPair) {
  const store = await cookies();
  store.set(ACCESS_COOKIE, tokens.access_token, cookieOptions(secondsUntilExpiry(tokens.access_token)));
  store.set(REFRESH_COOKIE, tokens.refresh_token, cookieOptions(secondsUntilExpiry(tokens.refresh_token)));
}

export async function clearTokens() {
  const store = await cookies();
  store.delete(ACCESS_COOKIE);
  store.delete(REFRESH_COOKIE);
}
