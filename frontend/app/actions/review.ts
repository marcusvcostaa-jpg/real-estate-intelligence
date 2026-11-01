"use server";

import { revalidatePath } from "next/cache";
import { apiPost } from "@/services/api";

export type DecisionState = { message?: string; error?: string } | undefined;

export async function decide(_: DecisionState, formData: FormData): Promise<DecisionState> {
  const id = String(formData.get("id") ?? "");
  const decision = String(formData.get("decision") ?? "");
  if (!/^\d+$/.test(id) || !["SAME_PROPERTY", "DIFFERENT"].includes(decision)) {
    return { error: "Pedido inválido." };
  }
  const { status, data } = await apiPost<{ detail?: string }>(`/dedup/candidates/${id}/decision`, { decision });
  if (status === 403) return { error: "Só administradores podem decidir." };
  if (status !== 200) return { error: data.detail ?? `Erro ${status}.` };
  revalidatePath("/review");
  return { message: decision === "SAME_PROPERTY" ? "Vendas unidas no mesmo imóvel." : "Marcados como imóveis diferentes." };
}
