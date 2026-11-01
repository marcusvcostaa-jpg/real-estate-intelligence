import type { Metadata } from "next";
import { Suspense } from "react";
import { BarChart } from "@/components/charts/bar-chart";
import { LineChart } from "@/components/charts/line-chart";
import { BASIS_PT, compactEur, eur, int } from "@/components/format";
import { apiGet } from "@/services/api";
import type { AreasResponse, PriceBands, TimeSeries } from "@/types/api";

export const metadata: Metadata = { title: "Análises · Real Estate Intelligence" };

// Categorical slots in fixed order; color follows the area (by position in the area list).
const SLOTS = ["var(--series-1)", "var(--series-2)", "var(--series-3)", "var(--series-4)"];
const UNAVAILABLE_LABELS: Record<string, string> = {
  price_per_m2: "Preço por m²",
  area: "Área média",
  bedrooms: "Quartos",
  bathrooms: "Banheiros",
  parking: "Vagas de garagem",
};

export default function AnalyticsPage({ searchParams }: PageProps<"/analytics">) {
  return (
    <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6">
      <h1 className="text-xl font-semibold tracking-tight">Análises de mercado</h1>
      <p className="mt-1 text-sm text-zinc-500">
        Preços <strong>transacionados</strong> do registro oficial (não preços anunciados).
      </p>
      <Suspense fallback={<p className="mt-6 text-sm text-zinc-500">Calculando…</p>}>
        <Analytics searchParams={searchParams} />
      </Suspense>
    </main>
  );
}

async function Analytics({ searchParams }: { searchParams: PageProps<"/analytics">["searchParams"] }) {
  const params = await searchParams;
  const { areas, unavailable } = await apiGet<AreasResponse>("/analytics/areas");
  const colorOf = new Map(areas.map((a, i) => [a.id, SLOTS[i % SLOTS.length]]));
  const requested = [params.areas ?? []].flat().map(Number).filter((id) => colorOf.has(id));
  const selected = (requested.length ? requested : areas.map((a) => a.id)).slice(0, 4);
  const bandRegion = typeof params.band === "string" && /^\d+$/.test(params.band) ? params.band : "";
  const [ts, bands] = await Promise.all([
    selected.length ? apiGet<TimeSeries>(`/analytics/timeseries?region_ids=${selected.join(",")}&months=120`) : null,
    apiGet<PriceBands>(`/analytics/price-bands${bandRegion ? `?region_id=${bandRegion}` : ""}`),
  ]);

  return (
    <div className="mt-6 space-y-10">
      <section aria-labelledby="cmp">
        <h2 id="cmp" className="text-base font-semibold">Comparação entre áreas</h2>
        <p className="text-xs text-zinc-500">Mediana dos últimos 12 meses · {BASIS_PT}.</p>
        <div className="mt-3">
          <BarChart
            ariaLabel="Mediana de preço por área nos últimos 12 meses"
            format="eur"
            bars={areas.map((a) => ({
              label: a.name,
              value: a.median_12m,
              detail: `${int.format(a.sales_12m)} vendas em 12 meses · média ${a.mean_12m ? eur.format(a.mean_12m) : "—"}`,
            }))}
          />
        </div>
        <div className="mt-4 overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-xs text-zinc-500">
              <tr>
                <th className="py-2 pr-4">Área</th>
                <th className="py-2 pr-4 text-right">Vendas (total)</th>
                <th className="py-2 pr-4 text-right">Vendas 12m</th>
                <th className="py-2 pr-4 text-right">Mediana 12m</th>
                <th className="py-2 pr-4 text-right">Média 12m</th>
                <th className="py-2 pr-4 text-right">Variação anual</th>
                <th className="py-2 pr-4 text-right">Novos 12m</th>
                <th className="py-2 pr-4 text-right">Imóveis revendidos</th>
              </tr>
            </thead>
            <tbody className="tabular-nums">
              {areas.map((a) => (
                <tr key={a.id} className="border-t border-zinc-100 dark:border-zinc-800">
                  <td className="py-2 pr-4">{a.name}</td>
                  <td className="py-2 pr-4 text-right">{int.format(a.sales)}</td>
                  <td className="py-2 pr-4 text-right">{int.format(a.sales_12m)}</td>
                  <td className="py-2 pr-4 text-right">{a.median_12m ? eur.format(a.median_12m) : "—"}</td>
                  <td className="py-2 pr-4 text-right">{a.mean_12m ? eur.format(a.mean_12m) : "—"}</td>
                  <td className="py-2 pr-4 text-right">
                    {a.median_change_pct === null ? "—" : `${a.median_change_pct > 0 ? "▲ +" : a.median_change_pct < 0 ? "▼ " : ""}${a.median_change_pct.toLocaleString("pt-BR")}%`}
                  </td>
                  <td className="py-2 pr-4 text-right">
                    {a.sales_12m ? `${Math.round((a.new_sales_12m / a.sales_12m) * 100)}%` : "—"}
                  </td>
                  <td className="py-2 pr-4 text-right">{int.format(a.repeat_sold_properties)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-2 text-xs text-zinc-500">
            Variação anual: mediana dos últimos 12 meses contra os 12 anteriores. A média fica acima da mediana por causa de vendas de alto valor (ex.: blocos inteiros); a mediana é a referência. &quot;Novos&quot;: imóveis vendidos como novos (preço geralmente sem IVA, fora da mediana).
          </p>
        </div>
      </section>

      <section aria-labelledby="hist">
        <h2 id="hist" className="text-base font-semibold">Histórico de preços</h2>
        <p className="text-xs text-zinc-500">
          Mediana mensal, últimos 10 anos · {BASIS_PT}. Trecho tracejado: meses recentes ainda incompletos no registro.
        </p>
        <form className="mt-3 flex flex-wrap items-center gap-3 text-sm" aria-label="Escolher áreas (até 4)">
          {areas.map((a) => (
            <label key={a.id} className="flex items-center gap-1.5">
              <input type="checkbox" name="areas" value={a.id} defaultChecked={selected.includes(a.id)} />
              {a.name}
            </label>
          ))}
          {bandRegion && <input type="hidden" name="band" value={bandRegion} />}
          <button type="submit" className="rounded-md border border-zinc-300 px-3 py-1 text-xs dark:border-zinc-700">
            Atualizar
          </button>
          {requested.length > 4 && <span className="text-xs text-zinc-500">Mostrando as 4 primeiras.</span>}
        </form>
        <div className="mt-3">
          {ts && (
            <LineChart
              ariaLabel="Mediana mensal de preço por área"
              yFormat="compactEur"
              xFormat="month"
              series={ts.series.map((s) => ({
                id: String(s.region_id),
                name: s.name,
                color: colorOf.get(s.region_id) ?? SLOTS[0],
                points: s.points.map((p) => ({ x: p.month, y: p.median, provisional: p.provisional, note: `${int.format(p.sales)} vendas` })),
              }))}
            />
          )}
        </div>
      </section>

      <section aria-labelledby="bands">
        <h2 id="bands" className="text-base font-semibold">Distribuição por faixa de preço</h2>
        <p className="text-xs text-zinc-500">{BASIS_PT}, últimos 12 meses.</p>
        <form className="mt-3 flex items-center gap-2 text-sm">
          {selected.map((id) => <input key={id} type="hidden" name="areas" value={id} />)}
          <select name="band" defaultValue={bandRegion} className="rounded-md border border-zinc-300 bg-transparent px-2 py-1 dark:border-zinc-700">
            <option value="">Todas as áreas</option>
            {areas.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
          </select>
          <button type="submit" className="rounded-md border border-zinc-300 px-3 py-1 text-xs dark:border-zinc-700">Atualizar</button>
        </form>
        <div className="mt-3">
          <BarChart
            orientation="vertical"
            ariaLabel="Vendas por faixa de preço"
            format="int"
            bars={bands.bands.map((b) => ({
              label: b.max ? `${compactEur(b.min)}–${compactEur(b.max)}` : `≥ ${compactEur(b.min)}`,
              value: b.sales,
            }))}
          />
        </div>
      </section>

      <section aria-labelledby="na">
        <h2 id="na" className="text-base font-semibold">Análises indisponíveis com as fontes atuais</h2>
        <ul className="mt-2 grid grid-cols-1 gap-2 text-sm sm:grid-cols-2 lg:grid-cols-5">
          {Object.entries(unavailable).map(([key, reason]) => (
            <li key={key} className="rounded-md border border-dashed border-zinc-300 p-3 dark:border-zinc-700">
              <p className="font-medium">{UNAVAILABLE_LABELS[key] ?? key}</p>
              <p className="text-xs text-zinc-500">Indisponível: {reason === "source has no floor area" ? "a fonte não informa a área" : reason === "source has no room counts" ? "a fonte não informa cômodos" : "a fonte não informa vagas"}.</p>
            </li>
          ))}
        </ul>
        <p className="mt-2 text-xs text-zinc-500">Esses indicadores aparecerão quando houver uma fonte autorizada com esses dados (ex.: anúncios). Nada é estimado.</p>
      </section>
    </div>
  );
}
