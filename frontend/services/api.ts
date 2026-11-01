import "server-only";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import type { CurrentUser, Health } from "@/types/api";
import { ACCESS_COOKIE, API_URL } from "./tokens";

async function token(): Promise<string> {
  const value = (await cookies()).get(ACCESS_COOKIE)?.value;
  if (!value) redirect("/login");
  return value;
}

/** GET an authenticated API path from server code; redirects to /login on 401. */
export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    headers: { Authorization: `Bearer ${await token()}` },
    cache: "no-store",
  });
  if (res.status === 401) redirect("/login");
  if (!res.ok) throw new Error(`API ${path} failed: ${res.status}`);
  return res.json();
}

/** POST JSON from a server action; returns status and parsed body (errors are not thrown). */
export async function apiPost<T>(path: string, body: unknown): Promise<{ status: number; data: T }> {
  const res = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: { Authorization: `Bearer ${await token()}`, "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (res.status === 401) redirect("/login");
  return { status: res.status, data: await res.json() };
}

export function getCurrentUser(): Promise<CurrentUser> {
  return apiGet<CurrentUser>("/auth/me");
}

export async function getHealth(): Promise<Health | null> {
  try {
    const res = await fetch(`${API_URL}/health`, { cache: "no-store" });
    return await res.json();
  } catch {
    return null;
  }
}
