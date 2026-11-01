"use client";

import {
  type ExpressionSpecification,
  type GeoJSONSource,
  LngLatBounds,
  Map as MapLibreMap,
  type MapMouseEvent,
  NavigationControl,
  setWorkerUrl,
} from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useRef, useState } from "react";
import { BASIS_PT } from "@/components/format";
import type { RegionCollection, RegionDetail, RegionStatus } from "@/types/api";

setWorkerUrl("/vendor/maplibre-worker"); // see app/vendor/maplibre-worker/route.ts

const STYLE_URL =
  process.env.NEXT_PUBLIC_MAP_STYLE_URL ?? "https://tiles.openfreemap.org/styles/positron";

export const STATUS: Record<RegionStatus, { label: string; color: string }> = {
  COMPLETED: { label: "Pesquisada", color: "#16a34a" },
  IN_PROGRESS: { label: "Em processamento", color: "#2563eb" },
  QUEUED: { label: "Na fila", color: "#f59e0b" },
  PARTIALLY_COMPLETED: { label: "Parcial", color: "#eab308" },
  FAILED: { label: "Falhou", color: "#dc2626" },
  REQUIRES_REVIEW: { label: "Requer revisão", color: "#9333ea" },
  NOT_STARTED: { label: "Pendente", color: "#9ca3af" },
};
const PRICE_STOPS: [number, string][] = [
  [250_000, "#dbeafe"],
  [350_000, "#93c5fd"],
  [450_000, "#3b82f6"],
  [600_000, "#1d4ed8"],
  [800_000, "#1e3a8a"],
];

type ColorMode = "status" | "price";

const eur = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "EUR", maximumFractionDigits: 0 });
const int = new Intl.NumberFormat("pt-BR");
const day = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString("pt-BR") : "—");

function fillColor(mode: ColorMode): ExpressionSpecification {
  if (mode === "price") {
    return [
      "case",
      ["==", ["get", "median_12m"], null],
      "#e5e7eb",
      ["step", ["get", "median_12m"], PRICE_STOPS[0][1], ...PRICE_STOPS.slice(1).flatMap(([v, c]) => [v, c])],
    ] as unknown as ExpressionSpecification; // built dynamically from STATUS / PRICE_STOPS
  }
  return [
    "match",
    ["get", "status"],
    ...Object.entries(STATUS).flatMap(([status, s]) => [status, s.color]),
    "#9ca3af",
  ] as unknown as ExpressionSpecification; // built dynamically from STATUS / PRICE_STOPS
}

export function RegionMap({ initial, attributions }: { initial: RegionCollection; attributions: string[] }) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<MapLibreMap | null>(null);
  const [mode, setMode] = useState<ColorMode>("status");
  const [detail, setDetail] = useState<RegionDetail | null>(null);
  const [childrenOf, setChildrenOf] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function select(regionId: number) {
    setError(null);
    const res = await fetch(`/api/regions/${regionId}`);
    if (!res.ok) return setError(`Não foi possível carregar a região (${res.status}).`);
    setDetail(await res.json());
  }

  useEffect(() => {
    if (!container.current) return;
    const m = new MapLibreMap({
      container: container.current,
      style: STYLE_URL,
      center: [-7.6, 53.4],
      zoom: 6,
      attributionControl: { customAttribution: attributions },
    });
    map.current = m;
    m.addControl(new NavigationControl({ showCompass: false }), "top-right");
    m.on("load", () => {
      for (const id of ["regions", "children"]) {
        m.addSource(id, {
          type: "geojson",
          data: id === "regions" ? initial : { type: "FeatureCollection", features: [] },
        });
        m.addLayer({
          id: `${id}-fill`,
          type: "fill",
          source: id,
          paint: { "fill-color": fillColor("status"), "fill-opacity": id === "regions" ? 0.55 : 0.65 },
        });
        m.addLayer({
          id: `${id}-line`,
          type: "line",
          source: id,
          paint: { "line-color": "#1f2937", "line-width": id === "regions" ? 1 : 0.5 },
        });
        m.on("mouseenter", `${id}-fill`, () => (m.getCanvas().style.cursor = "pointer"));
        m.on("mouseleave", `${id}-fill`, () => (m.getCanvas().style.cursor = ""));
      }
      // One handler: a sub-region wins over the parent drawn underneath it.
      m.on("click", (e: MapMouseEvent) => {
        const [hit] = m.queryRenderedFeatures(e.point, { layers: ["children-fill", "regions-fill"] });
        if (hit?.properties?.id) void select(Number(hit.properties.id));
      });
    });
    return () => m.remove();
    // The map is created once; data and mode updates go through the effects below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const m = map.current;
    if (!m?.isStyleLoaded()) return;
    for (const id of ["regions", "children"]) m.setPaintProperty(`${id}-fill`, "fill-color", fillColor(mode));
  }, [mode]);


  async function showChildren(region: RegionDetail) {
    const res = await fetch(`/api/regions?parent_id=${region.id}`);
    if (!res.ok) return setError(`Não foi possível carregar as sub-regiões (${res.status}).`);
    const fc: RegionCollection = await res.json();
    const m = map.current;
    (m?.getSource("children") as GeoJSONSource | undefined)?.setData(fc);
    setChildrenOf(region.name);
    const coords = fc.features.flatMap((f) => (f.geometry.type === "Polygon" ? f.geometry.coordinates.flat() : f.geometry.type === "MultiPolygon" ? f.geometry.coordinates.flat(2) : []));
    if (m && coords.length) {
      const bounds = coords.reduce((b, c) => b.extend(c as [number, number]), new LngLatBounds(coords[0] as [number, number], coords[0] as [number, number]));
      m.fitBounds(bounds, { padding: 40 });
    }
  }

  function clearChildren() {
    (map.current?.getSource("children") as GeoJSONSource | undefined)?.setData({ type: "FeatureCollection", features: [] });
    setChildrenOf(null);
    map.current?.flyTo({ center: [-7.6, 53.4], zoom: 6 });
  }

  return (
    <div className="relative flex min-h-[70vh] flex-1 flex-col gap-4 lg:flex-row">
      <div className="relative min-h-[60vh] flex-1 overflow-hidden rounded-lg border border-zinc-200 dark:border-zinc-800">
        <div ref={container} style={{ position: "absolute", inset: 0 }} aria-label="Mapa de cobertura das regiões" />
        <div className="absolute left-3 top-3 rounded-md bg-white/95 p-3 text-xs shadow dark:bg-zinc-900/95">
          <div className="mb-2 flex gap-1" role="group" aria-label="Colorir por">
            {(["status", "price"] as const).map((m) => (
              <button
                key={m}
                onClick={() => setMode(m)}
                aria-pressed={mode === m}
                className={`rounded px-2 py-1 ${mode === m ? "bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900" : "bg-zinc-100 dark:bg-zinc-800"}`}
              >
                {m === "status" ? "Status" : "Mediana de preço"}
              </button>
            ))}
          </div>
          {mode === "status" ? (
            <ul className="space-y-1">
              {Object.values(STATUS).map((s) => (
                <li key={s.label} className="flex items-center gap-2">
                  <span className="inline-block h-3 w-3 rounded-sm" style={{ background: s.color }} />
                  {s.label}
                </li>
              ))}
            </ul>
          ) : (
            <div>
              <ul className="space-y-1">
                <li className="flex items-center gap-2"><span className="inline-block h-3 w-3 rounded-sm bg-[#e5e7eb]" />Sem dados</li>
                {PRICE_STOPS.map(([v, c], i) => (
                  <li key={v} className="flex items-center gap-2">
                    <span className="inline-block h-3 w-3 rounded-sm" style={{ background: c }} />
                    {i === 0 ? `< ${eur.format(PRICE_STOPS[1][0])}` : `≥ ${eur.format(v)}`}
                  </li>
                ))}
              </ul>
              <p className="mt-2 max-w-48 text-zinc-500">{BASIS_PT}, últimos 12 meses</p>
            </div>
          )}
          {childrenOf && (
            <button onClick={clearChildren} className="mt-2 underline">Ocultar sub-regiões de {childrenOf}</button>
          )}
        </div>
      </div>

      <aside className="w-full shrink-0 rounded-lg border border-zinc-200 p-4 text-sm lg:w-80 dark:border-zinc-800">
        {error && <p role="alert" className="mb-2 text-red-600">{error}</p>}
        {!detail ? (
          <p className="text-zinc-500">Clique em uma região para ver os detalhes.</p>
        ) : (
          <div className="space-y-3">
            <div>
              <h2 className="text-base font-semibold">{detail.name}</h2>
              <p className="text-zinc-500">
                {detail.parent_name ? `${detail.parent_name} · ` : ""}
                <span style={{ color: STATUS[detail.status].color }}>{STATUS[detail.status].label}</span>
              </p>
            </div>
            <dl className="grid grid-cols-2 gap-x-3 gap-y-1">
              <dt className="text-zinc-500">Vendas registradas</dt>
              <dd>{detail.sales != null ? int.format(detail.sales) : "—"}</dd>
              <dt className="text-zinc-500">Imóveis</dt>
              <dd>{int.format(detail.properties)}</dd>
              <dt className="text-zinc-500">Vendas (12 meses)*</dt>
              <dd>{detail.sales_12m != null ? int.format(detail.sales_12m) : "—"}</dd>
              <dt className="text-zinc-500">Mediana (12 meses)*</dt>
              <dd>{detail.median_12m != null ? eur.format(detail.median_12m) : "—"}</dd>
              <dt className="text-zinc-500">Última pesquisa</dt>
              <dd>{day(detail.last_searched_at)}</dd>
            </dl>
            <p className="text-xs text-zinc-500">* {BASIS_PT}, últimos 12 meses.</p>
            {detail.sales == null && detail.parent_id != null && (
              <p className="text-xs text-zinc-500">
                Vendas ainda não são localizadas neste nível: o registro de preços não traz coordenadas.
              </p>
            )}
            <div>
              <h3 className="font-medium">Cobertura por fonte</h3>
              {detail.coverage.length === 0 ? (
                <p className="text-zinc-500">{detail.parent_id ? "Herdada da região superior." : "Nenhuma pesquisa ainda."}</p>
              ) : (
                <ul className="mt-1 space-y-1">
                  {detail.coverage.map((c) => (
                    <li key={c.source}>
                      <span className="font-mono text-xs">{c.source}</span> — {STATUS[c.status].label}, {int.format(c.records)} registros
                      <br />
                      <span className="text-xs text-zinc-500">concluída {day(c.last_completed_at)} · próxima {day(c.next_due_at)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            {detail.neighbors.length > 0 && (
              <p><span className="text-zinc-500">Vizinhas: </span>{detail.neighbors.join(", ")}</p>
            )}
            {detail.children > 0 && (
              <button
                onClick={() => void showChildren(detail)}
                className="w-full rounded-md bg-zinc-900 px-3 py-2 font-medium text-white dark:bg-zinc-100 dark:text-zinc-900"
              >
                Ver {int.format(detail.children)} sub-regiões
              </button>
            )}
          </div>
        )}
      </aside>
    </div>
  );
}
