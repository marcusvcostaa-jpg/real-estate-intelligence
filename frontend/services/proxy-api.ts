import "server-only";
import type { NextRequest } from "next/server";
import { ACCESS_COOKIE, API_URL } from "./tokens";

/** Backend-for-frontend: forwards a browser GET to the API with the httpOnly access token. */
export async function forwardGet(request: NextRequest, path: string): Promise<Response> {
  const token = request.cookies.get(ACCESS_COOKIE)?.value;
  if (!token) return Response.json({ detail: "Not authenticated" }, { status: 401 });
  const res = await fetch(`${API_URL}${path}`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });
  return new Response(res.body, {
    status: res.status,
    headers: { "content-type": res.headers.get("content-type") ?? "application/json" },
  });
}
