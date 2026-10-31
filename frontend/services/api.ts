import "server-only";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import type { CurrentUser, Health } from "@/types/api";
import { ACCESS_COOKIE, API_URL } from "./tokens";

export async function getCurrentUser(): Promise<CurrentUser> {
  const token = (await cookies()).get(ACCESS_COOKIE)?.value;
  if (!token) redirect("/login");
  const res = await fetch(`${API_URL}/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });
  if (res.status === 401) redirect("/login");
  if (!res.ok) throw new Error(`API /auth/me failed: ${res.status}`);
  return res.json();
}

export async function getHealth(): Promise<Health | null> {
  try {
    const res = await fetch(`${API_URL}/health`, { cache: "no-store" });
    return await res.json();
  } catch {
    return null;
  }
}
