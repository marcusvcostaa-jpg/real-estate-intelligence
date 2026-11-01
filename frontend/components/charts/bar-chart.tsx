"use client";

import { useState } from "react";
import { FORMATS, type FormatName } from "@/components/format";

export type Bar = { label: string; value: number | null; detail?: string };

/** Single-series bars (one color, no legend): horizontal for ranked categories, vertical for
 * ordered bins. 4px rounded data end, value at the tip, hover tooltip, table view. */
export function BarChart({
  bars,
  format: formatName,
  orientation = "horizontal",
  ariaLabel,
  color = "var(--series-1)",
}: {
  bars: Bar[];
  format: FormatName;
  orientation?: "horizontal" | "vertical";
  ariaLabel: string;
  color?: string;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const format = FORMATS[formatName];
  const max = Math.max(...bars.map((b) => b.value ?? 0), 1);
  const horizontal = orientation === "horizontal";
  const W = 720;
  const band = horizontal ? 30 : Math.min(90, (W - 40) / Math.max(bars.length, 1));
  const H = horizontal ? bars.length * band + 8 : 240;
  const labelW = horizontal ? 150 : 0;
  const plot = horizontal ? W - labelW - 90 : H - 48;

  return (
    <figure className="relative" style={{ color: "var(--viz-text-primary)" }}>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label={ariaLabel}>
        {bars.map((b, i) => {
          const len = b.value ? (b.value / max) * plot : 0;
          const thick = band - 10;
          // Rounded only at the data end (r = 4), anchored at the baseline.
          const r = Math.min(4, len / 2);
          const d = horizontal
            ? `M${labelW},${i * band + 4} h${len - r} q${r},0 ${r},${r} v${thick - 2 * r} q0,${r} -${r},${r} h-${len - r} z`
            : `M${20 + i * band + 5},${H - 24} v-${len - r} q0,-${r} ${r},-${r} h${thick - 2 * r} q${r},0 ${r},${r} v${len - r} z`;
          const cx = horizontal ? labelW : 20 + i * band + 5;
          return (
            <g key={b.label} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
              {/* hit target larger than the mark */}
              <rect
                x={horizontal ? 0 : cx - 5}
                y={horizontal ? i * band : 0}
                width={horizontal ? W : band}
                height={horizontal ? band : H}
                fill="transparent"
              />
              {len > 0 && <path d={d} fill={color} opacity={hover === null || hover === i ? 1 : 0.55} />}
              {horizontal ? (
                <>
                  <text x={labelW - 8} y={i * band + 4 + thick / 2} dy="0.32em" textAnchor="end" fontSize={12} fill="var(--viz-text-primary)">
                    {b.label}
                  </text>
                  <text x={labelW + len + 6} y={i * band + 4 + thick / 2} dy="0.32em" fontSize={12} fill="var(--viz-text-secondary)">
                    {b.value === null ? "sem dados" : format(b.value)}
                  </text>
                </>
              ) : (
                <>
                  <text x={cx + thick / 2} y={H - 8} textAnchor="middle" fontSize={11} fill="var(--viz-text-secondary)">
                    {b.label}
                  </text>
                  <text x={cx + thick / 2} y={H - 24 - len - 6} textAnchor="middle" fontSize={11} fill="var(--viz-text-primary)">
                    {b.value === null ? "" : format(b.value)}
                  </text>
                </>
              )}
            </g>
          );
        })}
      </svg>
      {hover !== null && bars[hover].detail && (
        <div className="pointer-events-none absolute right-2 top-2 max-w-xs rounded-md border border-zinc-200 bg-white px-3 py-2 text-xs shadow dark:border-zinc-700 dark:bg-zinc-900">
          <p className="font-medium">{bars[hover].label}</p>
          <p>{bars[hover].detail}</p>
        </div>
      )}
      <details className="mt-2 text-xs">
        <summary className="cursor-pointer text-zinc-500">Ver tabela</summary>
        <table className="mt-2 w-full text-left">
          <tbody>
            {bars.map((b) => (
              <tr key={b.label} className="border-t border-zinc-100 dark:border-zinc-800">
                <td className="py-1 pr-3">{b.label}</td>
                <td className="py-1 pr-3">{b.value === null ? "sem dados" : format(b.value)}</td>
                <td className="py-1 text-zinc-500">{b.detail}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </figure>
  );
}
