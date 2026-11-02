import type { Metadata } from "next";
import { Suspense } from "react";
import { type Country, CountrySwitch, pickCountry } from "@/components/country-switch";
import { RegionMap } from "@/components/region-map";
import { apiGet } from "@/services/api";
import type { CoverageSummary, RegionCollection } from "@/types/api";

export const metadata: Metadata = { title: "Mapa · Real Estate Intelligence" };

export default function MapPage({ searchParams }: PageProps<"/map">) {
  return (
    <main className="mx-auto flex w-full max-w-7xl flex-1 flex-col px-4 py-6">
      <h1 className="text-xl font-semibold tracking-tight">Cobertura geográfica</h1>
      <Suspense fallback={<p className="text-sm text-zinc-500">Carregando mapa…</p>}>
        <MapData searchParams={searchParams} />
      </Suspense>
    </main>
  );
}

async function MapData({ searchParams }: { searchParams: PageProps<"/map">["searchParams"] }) {
  const params = await searchParams;
  const { countries } = await apiGet<{ countries: Country[] }>("/analytics/countries");
  const country = pickCountry(countries, params.country);
  const currency = countries.find((c) => c.iso2 === country)?.currency ?? "EUR";
  const [regions, summary] = await Promise.all([
    apiGet<RegionCollection>(`/regions?country=${country}`),
    apiGet<CoverageSummary>("/coverage/summary"),
  ]);
  return (
    <>
      <CountrySwitch countries={countries} current={country} path="/map" />
      <div className="mt-4 flex flex-1 flex-col">
        {/* key: a new country mounts a new map at that country's view */}
        <RegionMap key={country} initial={regions} attributions={summary.attributions} country={country} currency={currency} />
      </div>
    </>
  );
}
