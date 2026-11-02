import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import { type Country, CountrySwitch, pickCountry } from "@/components/country-switch";
import { day, int, money } from "@/components/format";
import { apiGet } from "@/services/api";
import type { AreasResponse, PropertyPage } from "@/types/api";

export const metadata: Metadata = { title: "Imóveis · Real Estate Intelligence" };

const FILTERS = ["region_id", "min_price", "max_price", "sold_from", "sold_to", "kind", "q", "full_market_only", "repeat_sales_only", "cursor"] as const;
const input = "w-full rounded-md border border-zinc-300 bg-transparent px-2 py-1 text-sm dark:border-zinc-700";

export default function PropertiesPage({ searchParams }: PageProps<"/properties">) {
  return (
    <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6">
      <h1 className="text-xl font-semibold tracking-tight">Imóveis</h1>
      <p className="mt-1 text-sm text-zinc-500">
        Filtros aplicados à <strong>última venda</strong> de cada imóvel · preços transacionados.
      </p>
      <Suspense fallback={<p className="mt-6 text-sm text-zinc-500">Carregando…</p>}>
        <Results searchParams={searchParams} />
      </Suspense>
    </main>
  );
}

async function Results({ searchParams }: { searchParams: PageProps<"/properties">["searchParams"] }) {
  const params = await searchParams;
  const query = new URLSearchParams();
  for (const key of FILTERS) {
    const value = params[key];
    if (typeof value === "string" && value.trim()) query.set(key, value.trim());
  }
  const { countries } = await apiGet<{ countries: Country[] }>("/analytics/countries");
  const country = pickCountry(countries, params.country);
  const currency = countries.find((c) => c.iso2 === country)?.currency ?? "EUR";
  query.set("country", country); // prices are only comparable within one currency
  const [page, { areas }] = await Promise.all([
    apiGet<PropertyPage>(`/properties?${query}`),
    apiGet<AreasResponse>(`/analytics/areas?country=${country}`),
  ]);
  const v = (key: string) => (typeof params[key] === "string" ? (params[key] as string) : "");
  const next = new URLSearchParams(query);
  if (page.next_cursor) next.set("cursor", page.next_cursor);

  return (
    <>
      <CountrySwitch countries={countries} current={country} path="/properties" />
      <form className="mt-4 grid grid-cols-2 gap-3 rounded-lg border border-zinc-200 p-4 text-sm md:grid-cols-4 lg:grid-cols-6 dark:border-zinc-800" aria-label="Filtros">
        <input type="hidden" name="country" value={country} />
        <label className="col-span-2">Endereço contém<input name="q" defaultValue={v("q")} className={input} /></label>
        <label>Área
          <select name="region_id" defaultValue={v("region_id")} className={input}>
            <option value="">Todas</option>
            {areas.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
          </select>
        </label>
        <label>Tipo de venda
          <select name="kind" defaultValue={v("kind")} className={input}>
            <option value="">Todas</option>
            <option value="second_hand">Usado</option>
            <option value="new">Novo</option>
          </select>
        </label>
        <label>Preço mínimo ({currency})<input name="min_price" type="number" min={0} step={1000} defaultValue={v("min_price")} className={input} /></label>
        <label>Preço máximo ({currency})<input name="max_price" type="number" min={0} step={1000} defaultValue={v("max_price")} className={input} /></label>
        <label>Vendido a partir de<input name="sold_from" type="date" defaultValue={v("sold_from")} className={input} /></label>
        <label>Vendido até<input name="sold_to" type="date" defaultValue={v("sold_to")} className={input} /></label>
        <label className="flex items-center gap-2"><input type="checkbox" name="full_market_only" value="true" defaultChecked={v("full_market_only") === "true"} />Só valor de mercado pleno</label>
        <label className="flex items-center gap-2"><input type="checkbox" name="repeat_sales_only" value="true" defaultChecked={v("repeat_sales_only") === "true"} />Só revendidos</label>
        <div className="col-span-2 flex items-end gap-2">
          <button type="submit" className="rounded-md bg-zinc-900 px-3 py-1.5 font-medium text-white dark:bg-zinc-100 dark:text-zinc-900">Filtrar</button>
          <Link href="/properties" className="text-xs text-zinc-500 underline">Limpar</Link>
        </div>
        <p className="col-span-full text-xs text-zinc-500">
          {country === "BR"
            ? "Quartos, banheiros e garagem: indisponíveis — a fonte não informa. A área construída do IPTU aparece no detalhe do imóvel."
            : "Área construída, quartos, banheiros e garagem: indisponíveis — a fonte atual não informa."}
        </p>
      </form>

      <div className="mt-4 overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="text-xs text-zinc-500">
            <tr>
              <th className="py-2 pr-4">Endereço</th>
              <th className="py-2 pr-4">Área</th>
              <th className="py-2 pr-4">{country === "BR" ? "CEP" : "Eircode"}</th>
              <th className="py-2 pr-4 text-right">Última venda</th>
              <th className="py-2 pr-4 text-right">Preço</th>
              <th className="py-2 pr-4">Observações</th>
              <th className="py-2 pr-4 text-right">Vendas</th>
            </tr>
          </thead>
          <tbody className="tabular-nums">
            {page.items.map((p) => (
              <tr key={p.public_id} className="border-t border-zinc-100 dark:border-zinc-800">
                <td className="py-2 pr-4"><Link href={`/properties/${p.public_id}`} className="underline-offset-2 hover:underline">{p.address_display ?? "—"}</Link></td>
                <td className="py-2 pr-4">{p.region}</td>
                <td className="py-2 pr-4 font-mono text-xs">{p.postal_code ?? "—"}</td>
                <td className="py-2 pr-4 text-right">{day(p.last_sale_date)}</td>
                <td className="py-2 pr-4 text-right">{money(p.last_sale_price, p.currency)}</td>
                <td className="py-2 pr-4 text-xs text-zinc-500">
                  {[p.last_is_new && "novo", p.last_vat_exclusive && "sem IVA", p.last_full_market === false && "abaixo do valor de mercado"].filter(Boolean).join(" · ") || "—"}
                </td>
                <td className="py-2 pr-4 text-right">{int.format(p.sales)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {page.items.length === 0 && <p className="py-6 text-sm text-zinc-500">Nenhum imóvel com esses filtros.</p>}
      </div>
      <div className="mt-4 flex justify-between text-sm">
        {query.has("cursor") ? <Link href={`/properties?${new URLSearchParams([...query].filter(([k]) => k !== "cursor"))}`} className="underline">Primeira página</Link> : <span />}
        {page.next_cursor && <Link href={`/properties?${next}`} className="underline">Próxima página →</Link>}
      </div>
    </>
  );
}
