import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import { RegionMap } from "@/components/region-map";
import { apiGet } from "@/services/api";
import type { CoverageSummary, RegionCollection } from "@/types/api";

export const metadata: Metadata = { title: "Mapa · Real Estate Intelligence" };

export default function MapPage() {
  return (
    <main className="mx-auto flex w-full max-w-7xl flex-1 flex-col px-4 py-6">
      <div className="mb-4 flex items-baseline justify-between gap-4">
        <h1 className="text-xl font-semibold tracking-tight">Cobertura geográfica</h1>
        <Link href="/" className="text-sm text-zinc-500 underline">Início</Link>
      </div>
      <Suspense fallback={<p className="text-sm text-zinc-500">Carregando mapa…</p>}>
        <MapData />
      </Suspense>
    </main>
  );
}

async function MapData() {
  const [regions, summary] = await Promise.all([
    apiGet<RegionCollection>("/regions"),
    apiGet<CoverageSummary>("/coverage/summary"),
  ]);
  return <RegionMap initial={regions} attributions={summary.attributions} />;
}
