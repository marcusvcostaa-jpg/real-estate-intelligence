"use client";

import { useActionState } from "react";
import { decide } from "@/app/actions/review";

export function DecisionButtons({ id, canDecide }: { id: number; canDecide: boolean }) {
  const [state, action, pending] = useActionState(decide, undefined);
  if (!canDecide) return <span className="text-xs text-zinc-500">Somente ADMIN decide.</span>;
  if (state?.message) return <span className="text-xs text-zinc-500">{state.message}</span>;
  return (
    <form action={action} className="flex flex-wrap items-center gap-2">
      <input type="hidden" name="id" value={id} />
      <button name="decision" value="SAME_PROPERTY" disabled={pending} className="rounded-md bg-zinc-900 px-2 py-1 text-xs font-medium text-white disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900">
        Mesmo imóvel
      </button>
      <button name="decision" value="DIFFERENT" disabled={pending} className="rounded-md border border-zinc-300 px-2 py-1 text-xs disabled:opacity-50 dark:border-zinc-700">
        Imóveis diferentes
      </button>
      {state?.error && <span role="alert" className="text-xs text-red-600">{state.error}</span>}
    </form>
  );
}
