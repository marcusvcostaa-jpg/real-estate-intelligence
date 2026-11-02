"use server";

import { revalidatePath } from "next/cache";
import { apiPost } from "@/services/api";

export type CollectState = { message?: string; error?: string } | undefined;

export async function requestCollection(_: CollectState, formData: FormData): Promise<CollectState> {
  const regionId = String(formData.get("region_id") ?? "");
  const source = String(formData.get("source") ?? "");
  if (!/^\d+$/.test(regionId) || !/^[a-z0-9_]+$/.test(source)) return { error: "Pedido inválido." };
  const { status, data } = await apiPost<{ id?: number; detail?: string }>("/collection/requests", {
    region_id: Number(regionId),
    source,
  });
  if (status === 403) return { error: "Só administradores pedem coletas." };
  if (status !== 201) return { error: data.detail ?? `Erro ${status}.` };
  revalidatePath("/collect");
  return { message: `Na fila (job ${data.id}); começa em até 5 min.` };
}
