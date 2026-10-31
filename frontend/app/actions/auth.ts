"use server";

import { redirect } from "next/navigation";
import { clearTokens, storeTokens } from "@/services/session";
import { API_URL, type TokenPair } from "@/services/tokens";

export type LoginState = { error?: string } | undefined;

export async function login(_: LoginState, formData: FormData): Promise<LoginState> {
  const email = String(formData.get("email") ?? "").trim();
  const password = String(formData.get("password") ?? "");
  if (!email || !password) return { error: "Informe e-mail e senha." };

  let res: Response;
  try {
    res = await fetch(`${API_URL}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
      cache: "no-store",
    });
  } catch {
    return { error: "API indisponível. Tente novamente em instantes." };
  }
  if (res.status === 401) return { error: "E-mail ou senha inválidos." };
  if (res.status === 429) return { error: "Muitas tentativas. Aguarde um minuto." };
  if (!res.ok) return { error: `Erro inesperado (${res.status}).` };

  await storeTokens((await res.json()) as TokenPair);
  redirect("/");
}

export async function logout() {
  await clearTokens();
  redirect("/login");
}
