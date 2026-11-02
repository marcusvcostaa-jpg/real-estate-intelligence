"use client";

import { useActionState } from "react";
import { requestCollection } from "@/app/actions/collect";

export function RequestButton({ regionId, source }: { regionId: number; source: string }) {
  const [state, action, pending] = useActionState(requestCollection, undefined);
  if (state?.message) return <span className="text-xs text-zinc-500">{state.message}</span>;
  return (
    <form action={action} className="flex flex-wrap items-center gap-2">
      <input type="hidden" name="region_id" value={regionId} />
      <input type="hidden" name="source" value={source} />
      <button disabled={pending} className="rounded-md bg-zinc-900 px-2 py-1 text-xs font-medium text-white disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900">
        {pending ? "Enviando…" : "Coletar agora"}
      </button>
      {state?.error && <span role="alert" className="text-xs text-red-600">{state.error}</span>}
    </form>
  );
}
