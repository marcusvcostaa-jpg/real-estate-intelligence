import Link from "next/link";
import { Suspense } from "react";
import { day, int } from "@/components/format";
import { apiGet, getHealth } from "@/services/api";
import type { CoverageSummary, Kpis } from "@/types/api";

export default function Home() {
  return (
    <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6">
      <h1 className="text-xl font-semibold tracking-tight">Visão geral</h1>
      <p className="mt-1 text-sm text-zinc-500">
        Preços <strong>transacionados</strong> (registros oficiais) — não são preços anunciados.
      </p>
      <Suspense fallback={<p className="mt-6 text-sm text-zinc-500">Carregando indicadores…</p>}>
        <Indicators />
      </Suspense>
    </main>
  );
}

function Tile({ label, value, hint, href }: { label: string; value: string; hint?: string; href?: string }) {
  const body = (
    <div className="h-full rounded-lg border border-zinc-200 p-4 dark:border-zinc-800">
      <p className="text-xs text-zinc-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums">{value}</p>
      {hint && <p className="mt-1 text-xs text-zinc-500">{hint}</p>}
    </div>
  );
  return href ? <Link href={href} className="block hover:opacity-80">{body}</Link> : body;
}

async function Indicators() {
  const [k, summary, health] = await Promise.all([
    apiGet<Kpis>("/analytics/kpis"),
    apiGet<CoverageSummary>("/coverage/summary"),
    getHealth(),
  ]);
  return (
    <>
      <section className="mt-6 grid grid-cols-2 gap-3 md:grid-cols-4" aria-label="Indicadores">
        <Tile label="Imóveis cadastrados" value={int.format(k.properties)} hint="imóveis físicos, após deduplicação" href="/properties" />
        <Tile label="Vendas registradas" value={int.format(k.transactions)} hint="preços transacionados" href="/analytics" />
        <Tile label="Anúncios" value={int.format(k.listings)} hint={k.listings ? undefined : "nenhuma fonte de anúncios autorizada ainda"} />
        <Tile label="Áreas pesquisadas" value={`${k.areas_researched} de ${k.areas_total}`} hint="condados" href="/map" />
        <Tile label="Regiões pesquisadas" value={int.format(k.regions_researched)} hint="todas as subdivisões" href="/map" />
        <Tile label="Regiões pendentes" value={int.format(k.regions_pending)} />
        <Tile label="Em processamento" value={int.format(k.regions_in_progress)} hint={`${int.format(k.jobs_queued)} jobs na fila`} />
        <Tile label="Imóveis novos no sistema (7 dias)" value={int.format(k.new_properties_7d)} hint="cadastrados pela coleta, não imóveis novos no mercado" />
        <Tile label="Fontes ativas" value={int.format(k.active_sources)} />
        <Tile label="Última atualização" value={day(k.last_update)} />
        <Tile label="Revisões pendentes" value={int.format(k.review_pending)} hint="possíveis duplicados" href="/review" />
        <Tile
          label="Sistema"
          value={health?.status === "ok" ? "Operacional" : "Degradado"}
          hint={health ? `banco ${health.db} · fila ${health.redis}` : "API indisponível"}
        />
      </section>
      <p className="mt-6 text-xs text-zinc-500">{summary.attributions.join(" · ")}</p>
    </>
  );
}
