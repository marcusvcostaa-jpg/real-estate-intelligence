import "server-only";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import type { CurrentUser, Health } from "@/types/api";
import { ACCESS_COOKIE, API_URL } from "./tokens";

/** GET an authenticated API path from server code; redirects to /login on 401. */
export async function apiGet<T>(path: string): Promise<T> {
  const token = (await cookies()).get(ACCESS_COOKIE)?.value;
  if (!token) redirect("/login");
  const res = await fetch(`${API_URL}${path}`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });
  if (res.status === 401) redirect("/login");
  if (!res.ok) throw new Error(`API ${path} failed: ${res.status}`);
  return res.json();
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
