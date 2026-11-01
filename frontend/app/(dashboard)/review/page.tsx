import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import { day, eur, int } from "@/components/format";
import { apiGet, getCurrentUser } from "@/services/api";
import type { ReviewQueue } from "@/types/api";
import { DecisionButtons } from "./decision-buttons";

export const metadata: Metadata = { title: "Revisão · Real Estate Intelligence" };

const REASONS: Record<string, string> = {
  fuzzy: "endereços parecidos, um com palavras a mais",
  address: "mesmo endereço, vendas na mesma data",
  eircode: "mesmo Eircode, vendas na mesma data",
};

export default function ReviewPage({ searchParams }: PageProps<"/review">) {
  return (
    <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6">
      <h1 className="text-xl font-semibold tracking-tight">Revisão de possíveis duplicados</h1>
      <p className="mt-1 text-sm text-zinc-500">
        Casos em que o algoritmo não teve certeza. &quot;Mesmo imóvel&quot; move a venda para o imóvel candidato; nenhuma venda é apagada e as próximas deduplicações respeitam a decisão.
      </p>
      <Suspense fallback={<p className="mt-6 text-sm text-zinc-500">Carregando…</p>}>
        <Queue searchParams={searchParams} />
      </Suspense>
    </main>
  );
}

async function Queue({ searchParams }: { searchParams: PageProps<"/review">["searchParams"] }) {
  const params = await searchParams;
  const after = typeof params.after === "string" && /^\d+$/.test(params.after) ? params.after : "0";
  const user = await getCurrentUser();
  if (user.role === "VIEWER") return <p className="mt-6 text-sm">A fila de revisão é restrita a analistas e administradores.</p>;
  const queue = await apiGet<ReviewQueue>(`/dedup/candidates?limit=25&after_id=${after}`);
  const last = queue.items.at(-1);
  return (
    <>
      <p className="mt-4 text-sm">{int.format(queue.total)} pares pendentes.</p>
      <ul className="mt-3 space-y-3">
        {queue.items.map((c) => (
          <li key={c.id} className="rounded-lg border border-zinc-200 p-4 text-sm dark:border-zinc-800">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="grid flex-1 gap-3 md:grid-cols-2">
                <div>
                  <p className="text-xs text-zinc-500">Venda</p>
                  <p className="font-medium">{c.sale_address}</p>
                  <p className="text-xs text-zinc-500">{day(c.sale_date)} · {eur.format(c.sale_price)} · Eircode {c.sale_eircode ?? "—"}</p>
                </div>
                <div>
                  <p className="text-xs text-zinc-500">Imóvel candidato ({c.region})</p>
                  <p className="font-medium">
                    <Link href={`/properties/${c.candidate_public_id}`} className="hover:underline">{c.candidate_address}</Link>
                  </p>
                  <p className="text-xs text-zinc-500">{int.format(c.candidate_sales)} venda(s) · Eircode {c.candidate_eircode ?? "—"}</p>
                </div>
              </div>
              <DecisionButtons id={c.id} canDecide={user.role === "ADMIN"} />
            </div>
            <p className="mt-2 text-xs text-zinc-500">
              Motivo: {REASONS[c.method] ?? c.method} · similaridade {Math.round(c.score * 100)}%
              {c.vetoes.length > 0 && ` · vetos: ${c.vetoes.join(", ")}`}
            </p>
          </li>
        ))}
      </ul>
      {last && queue.items.length === 25 && (
        <Link href={`/review?after=${last.id}`} className="mt-4 inline-block text-sm underline">Próximos →</Link>
      )}
    </>
  );
}
