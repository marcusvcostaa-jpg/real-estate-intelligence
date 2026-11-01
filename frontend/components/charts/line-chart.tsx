"use client";

import { useMemo, useState } from "react";
import { FORMATS, type FormatName, X_FORMATS, type XFormatName } from "@/components/format";

export type LinePoint = { x: string; y: number; provisional?: boolean; note?: string };
export type LineSeries = { id: string; name: string; color: string; points: LinePoint[] };

const W = 720;
const H = 300;
const M = { top: 16, right: 120, bottom: 28, left: 64 };

function niceTicks(min: number, max: number, count = 5): number[] {
  const span = max - min || Math.abs(max) || 1;
  const step0 = span / count;
  const mag = 10 ** Math.floor(Math.log10(step0));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => span / s <= count) ?? mag * 10;
  const start = Math.floor(min / step) * step;
  const ticks = [];
  for (let v = start; v <= max + step * 0.5; v += step) ticks.push(v);
  return ticks;
}

/** Multi-series line chart: one y-axis, 2px lines, legend + direct end labels (<= 4 series),
 * crosshair tooltip, dashed tail for provisional points, table view for accessibility. */
export function LineChart({
  series,
  yFormat: yFormatName,
  xFormat: xFormatName,
  ariaLabel,
}: {
  series: LineSeries[];
  yFormat: FormatName;
  xFormat: XFormatName;
  ariaLabel: string;
}) {
  const yFormat = FORMATS[yFormatName];
  const xFormat = X_FORMATS[xFormatName];
  const [hover, setHover] = useState<number | null>(null);
  const xs = useMemo(() => [...new Set(series.flatMap((s) => s.points.map((p) => p.x)))].sort(), [series]);
  const values = series.flatMap((s) => s.points.map((p) => p.y));
  if (!xs.length || !values.length) return <p className="text-sm text-zinc-500">Sem dados para o período.</p>;

  const ticks = niceTicks(Math.min(...values), Math.max(...values));
  const [y0, y1] = [ticks[0], ticks[ticks.length - 1]];
  // x values are ISO dates: position by real time, so uneven gaps (years vs months) stay honest.
  const ts = xs.map((x) => Date.parse(x));
  const [t0, t1] = [ts[0], ts[ts.length - 1]];
  const px = (i: number) => M.left + (t1 === t0 ? 0 : ((ts[i] - t0) / (t1 - t0)) * (W - M.left - M.right));
  const py = (v: number) => M.top + (1 - (v - y0) / (y1 - y0 || 1)) * (H - M.top - M.bottom);
  const xi = new Map(xs.map((x, i) => [x, i]));
  const path = (pts: LinePoint[]) => pts.map((p, i) => `${i ? "L" : "M"}${px(xi.get(p.x)!)},${py(p.y)}`).join("");
  const labelEvery = Math.max(1, Math.ceil(xs.length / 8));
  const showMarkers = xs.length <= 24; // sparse series: show each observation (>= 8px)

  // X labels that fit: keep the last one, drop any closer than MIN_GAP to an already kept label.
  const MIN_GAP = 72;
  const xLabels: number[] = [];
  const candidates = xs.map((_, i) => i).filter((i) => i % labelEvery === 0 && i !== xs.length - 1);
  for (const i of [xs.length - 1, ...candidates]) {
    if (xLabels.every((j) => Math.abs(px(i) - px(j)) >= MIN_GAP)) xLabels.push(i);
  }

  // Direct end labels, nudged apart so they never overlap.
  const ends = (series.length > 1 ? series : []) // one series: the title names it, no label needed
    .filter((s) => s.points.length)
    .map((s) => ({ s, y: py(s.points[s.points.length - 1].y) }))
    .sort((a, b) => a.y - b.y);
  for (let i = 1; i < ends.length; i++) ends[i].y = Math.max(ends[i].y, ends[i - 1].y + 14);

  function onMove(e: React.MouseEvent<SVGRectElement>) {
    const rect = e.currentTarget.ownerSVGElement!.getBoundingClientRect();
    const x = ((e.clientX - rect.left) / rect.width) * W;
    let nearest = 0;
    for (let i = 1; i < xs.length; i++) if (Math.abs(px(i) - x) < Math.abs(px(nearest) - x)) nearest = i;
    setHover(nearest);
  }

  const hx = hover === null ? null : xs[hover];
  return (
    <figure className="relative" style={{ color: "var(--viz-text-primary)" }}>
      {series.length > 1 && (
        <ul className="mb-2 flex flex-wrap gap-3 text-xs" aria-label="Legenda">
          {series.map((s) => (
            <li key={s.id} className="flex items-center gap-1.5" style={{ color: "var(--viz-text-secondary)" }}>
              <span className="inline-block h-0.5 w-4 rounded" style={{ background: s.color }} />
              {s.name}
            </li>
          ))}
        </ul>
      )}
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label={ariaLabel} className="overflow-visible">
        {ticks.map((t) => (
          <g key={t}>
            <line x1={M.left} x2={W - M.right} y1={py(t)} y2={py(t)} stroke="var(--viz-grid)" strokeWidth={1} />
            <text x={M.left - 8} y={py(t)} dy="0.32em" textAnchor="end" fontSize={11} fill="var(--viz-text-secondary)">
              {yFormat(t)}
            </text>
          </g>
        ))}
        {xLabels.map((i) => (
          <text key={xs[i]} x={px(i)} y={H - 8} textAnchor="middle" fontSize={11} fill="var(--viz-text-secondary)">
            {xFormat(xs[i])}
          </text>
        ))}
        {series.map((s) => {
          const firstProv = s.points.findIndex((p) => p.provisional);
          const solid = firstProv === -1 ? s.points : s.points.slice(0, firstProv);
          const dashed = firstProv === -1 ? [] : s.points.slice(Math.max(0, firstProv - 1));
          return (
            <g key={s.id}>
              <path d={path(solid)} fill="none" stroke={s.color} strokeWidth={2} strokeLinejoin="round" />
              {dashed.length > 1 && (
                <path d={path(dashed)} fill="none" stroke={s.color} strokeWidth={2} strokeDasharray="4 4" />
              )}
              {showMarkers &&
                s.points.map((p) => (
                  <circle key={p.x} cx={px(xi.get(p.x)!)} cy={py(p.y)} r={4} fill={s.color} stroke="var(--viz-surface)" strokeWidth={2} />
                ))}
            </g>
          );
        })}
        {ends.map(({ s, y }) => (
          <g key={s.id}>
            <circle cx={W - M.right + 8} cy={y} r={4} fill={s.color} />
            <text x={W - M.right + 16} y={y} dy="0.32em" fontSize={11} fill="var(--viz-text-primary)">
              {s.name}
            </text>
          </g>
        ))}
        {hx !== null && (
          <g pointerEvents="none">
            <line x1={px(hover!)} x2={px(hover!)} y1={M.top} y2={H - M.bottom} stroke="var(--viz-text-secondary)" strokeWidth={1} />
            {series.map((s) => {
              const p = s.points.find((q) => q.x === hx);
              return p ? (
                <circle key={s.id} cx={px(hover!)} cy={py(p.y)} r={4} fill={s.color} stroke="var(--viz-surface)" strokeWidth={2} />
              ) : null;
            })}
          </g>
        )}
        <rect
          x={M.left}
          y={M.top}
          width={W - M.left - M.right}
          height={H - M.top - M.bottom}
          fill="transparent"
          onMouseMove={onMove}
          onMouseLeave={() => setHover(null)}
        />
      </svg>
      {hx !== null && (
        <div
          className="pointer-events-none absolute top-8 rounded-md border border-zinc-200 bg-white px-3 py-2 text-xs shadow dark:border-zinc-700 dark:bg-zinc-900"
          style={{ left: `${Math.min((px(hover!) / W) * 100, 70)}%` }}
        >
          <p className="font-medium">{xFormat(hx)}</p>
          {series.map((s) => {
            const p = s.points.find((q) => q.x === hx);
            return p ? (
              <p key={s.id} className="flex items-center gap-1.5">
                <span className="inline-block h-2 w-2 rounded-full" style={{ background: s.color }} />
                {s.name}: {yFormat(p.y)} {p.note ? <span className="text-zinc-500">({p.note})</span> : null}
                {p.provisional ? <span className="text-zinc-500">· provisório</span> : null}
              </p>
            ) : null;
          })}
        </div>
      )}
      <details className="mt-2 text-xs">
        <summary className="cursor-pointer text-zinc-500">Ver tabela</summary>
        <div className="mt-2 max-h-64 overflow-auto">
          <table className="w-full text-left">
            <thead>
              <tr>
                <th className="py-1 pr-3">Mês</th>
                {series.map((s) => <th key={s.id} className="py-1 pr-3">{s.name}</th>)}
              </tr>
            </thead>
            <tbody>
              {xs.map((x) => (
                <tr key={x} className="border-t border-zinc-100 dark:border-zinc-800">
                  <td className="py-1 pr-3">{xFormat(x)}</td>
                  {series.map((s) => {
                    const p = s.points.find((q) => q.x === x);
                    return <td key={s.id} className="py-1 pr-3">{p ? `${yFormat(p.y)}${p.provisional ? "*" : ""}` : "—"}</td>;
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </figure>
  );
}
