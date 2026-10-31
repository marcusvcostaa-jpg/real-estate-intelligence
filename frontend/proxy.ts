import { NextResponse, type NextRequest } from "next/server";
import { ACCESS_COOKIE, API_URL, REFRESH_COOKIE, cookieOptions, secondsUntilExpiry, type TokenPair } from "@/services/tokens";

// Optimistic gate: the access cookie expires together with the JWT, so a missing access
// cookie means "refresh or log in". Real authorization still happens in the API.
export async function proxy(request: NextRequest) {
  if (request.cookies.has(ACCESS_COOKIE)) return NextResponse.next();

  const refreshToken = request.cookies.get(REFRESH_COOKIE)?.value;
  if (refreshToken) {
    const res = await fetch(`${API_URL}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    }).catch(() => null);
    if (res?.ok) {
      const tokens = (await res.json()) as TokenPair;
      // Redirect to the same URL so the page renders with the new cookies.
      const response = NextResponse.redirect(request.url);
      response.cookies.set(ACCESS_COOKIE, tokens.access_token, cookieOptions(secondsUntilExpiry(tokens.access_token)));
      response.cookies.set(REFRESH_COOKIE, tokens.refresh_token, cookieOptions(secondsUntilExpiry(tokens.refresh_token)));
      return response;
    }
  }

  const response = NextResponse.redirect(new URL("/login", request.url));
  response.cookies.delete(REFRESH_COOKIE);
  return response;
}

export const config = {
  matcher: ["/((?!login|_next/static|_next/image|favicon.ico).*)"],
};
