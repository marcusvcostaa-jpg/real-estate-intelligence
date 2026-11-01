import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import { LineChart } from "@/components/charts/line-chart";
import { day, eur } from "@/components/format";
import { apiGet } from "@/services/api";
import type { PropertyDetail } from "@/types/api";

export const metadata: Metadata = { title: "Imóvel · Real Estate Intelligence" };

export default function PropertyPage({ params }: PageProps<"/properties/[id]">) {
  return (
    <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-6">
      <Link href="/properties" className="text-sm text-zinc-500 underline">← Imóveis</Link>
      <Suspense fallback={<p className="mt-6 text-sm text-zinc-500">Carregando…</p>}>
        <Detail params={params} />
      </Suspense>
    </main>
  );
}

async function Detail({ params }: { params: PageProps<"/properties/[id]">["params"] }) {
  const { id } = await params;
  if (!/^[0-9a-f-]{36}$/i.test(id)) return <p className="mt-6 text-sm">Imóvel inválido.</p>;
  const p = await apiGet<PropertyDetail>(`/properties/${id}`);
  return (
    <div className="mt-4 space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">{p.address_display ?? "Endereço não informado"}</h1>
        <p className="text-sm text-zinc-500">
          {p.region} · Eircode {p.postal_code ?? "—"} · tipo {p.property_type === "DWELLING" ? "residência (casa ou apartamento — a fonte não distingue)" : p.property_type}
        </p>
        {p.pending_reviews > 0 && (
          <p className="mt-1 text-sm">
            <Link href="/review" className="underline">{p.pending_reviews} possível(is) duplicado(s) aguardando revisão</Link>
          </p>
        )}
      </div>
      {p.sales.length > 1 && (
        <section aria-labelledby="hist">
          <h2 id="hist" className="text-base font-semibold">Histórico de vendas</h2>
          <LineChart
            ariaLabel="Preço de cada venda deste imóvel"
            yFormat="compactEur"
            xFormat="day"
            series={[{ id: "sales", name: "Preço transacionado", color: "var(--series-1)", points: p.sales.map((s) => ({ x: s.transaction_date, y: s.price, note: [s.vat_exclusive && "sem IVA", s.is_full_market_price === false && "abaixo do valor de mercado"].filter(Boolean).join(", ") || undefined })) }]}
          />
        </section>
      )}
      <section aria-labelledby="sales">
        <h2 id="sales" className="text-base font-semibold">Vendas registradas ({p.sales.length})</h2>
        <table className="mt-2 w-full text-left text-sm">
          <thead className="text-xs text-zinc-500">
            <tr>
              <th className="py-2 pr-4">Data</th>
              <th className="py-2 pr-4 text-right">Preço</th>
              <th className="py-2 pr-4">Observações</th>
              <th className="py-2 pr-4">Endereço como publicado</th>
              <th className="py-2 pr-4">Fonte</th>
            </tr>
          </thead>
          <tbody className="tabular-nums">
            {p.sales.map((s) => (
              <tr key={s.id} className="border-t border-zinc-100 dark:border-zinc-800">
                <td className="py-2 pr-4">{day(s.transaction_date)}</td>
                <td className="py-2 pr-4 text-right">{eur.format(s.price)}</td>
                <td className="py-2 pr-4 text-xs text-zinc-500">
                  {[s.description_original, s.vat_exclusive && "sem IVA", s.is_full_market_price === false && "abaixo do valor de mercado"].filter(Boolean).join(" · ")}
                </td>
                <td className="py-2 pr-4 text-xs">{s.address_original}</td>
                <td className="py-2 pr-4 font-mono text-xs">{s.source}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="mt-2 text-xs text-zinc-500">Preços transacionados (registro oficial). Um anúncio removido não significa venda; aqui só aparecem vendas registradas.</p>
      </section>
    </div>
  );
}
