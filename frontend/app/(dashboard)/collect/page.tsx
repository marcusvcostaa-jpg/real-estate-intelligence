import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import { type Country, CountrySwitch, pickCountry } from "@/components/country-switch";
import { day, int } from "@/components/format";
import { apiGet, getCurrentUser } from "@/services/api";
import type { CollectionPlace, JobRow } from "@/types/api";
import { RequestButton } from "./request-button";

export const metadata: Metadata = { title: "Coletas · Real Estate Intelligence" };

const STATUS: Record<string, string> = {
  NOT_STARTED: "nunca coletado",
  QUEUED: "na fila",
  IN_PROGRESS: "coletando",
  PARTIALLY_COMPLETED: "parcial",
  COMPLETED: "concluído",
  FAILED: "falhou",
  REQUIRES_REVIEW: "requer revisão",
  SKIPPED: "não executado",
  CANCELLED: "cancelado",
};

export default function CollectPage({ searchParams }: PageProps<"/collect">) {
  return (
    <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6">
      <h1 className="text-xl font-semibold tracking-tight">Coletas</h1>
      <p className="mt-1 text-sm text-zinc-500">
        Lugares que as fontes aprovadas cobrem. O orquestrador atualiza e expande sozinho; &quot;Coletar agora&quot; põe um lugar na frente da fila, respeitando o intervalo mínimo de cada fonte. Para consultar o que já está no banco, use{" "}
        <Link href="/properties" className="underline">Imóveis</Link>.
      </p>
      <Suspense fallback={<p className="mt-6 text-sm text-zinc-500">Carregando…</p>}>
        <Places searchParams={searchParams} />
      </Suspense>
    </main>
  );
}

async function Places({ searchParams }: { searchParams: PageProps<"/collect">["searchParams"] }) {
  const params = await searchParams;
  const [user, { countries }] = await Promise.all([getCurrentUser(), apiGet<{ countries: Country[] }>("/analytics/countries")]);
  const country = pickCountry(countries, params.country);
  const [places, jobs] = await Promise.all([
    apiGet<CollectionPlace[]>(`/collection/places?country=${country}`),
    user.role === "VIEWER" ? Promise.resolve([]) : apiGet<JobRow[]>("/jobs?limit=15"),
  ]);
  const cell = "px-3 py-2";

  return (
    <>
      <CountrySwitch countries={countries} current={country} path="/collect" />
      <div className="mt-4 overflow-x-auto rounded-lg border border-zinc-200 dark:border-zinc-800">
        <table className="w-full text-left text-sm">
          <thead className="bg-zinc-50 text-xs text-zinc-500 dark:bg-zinc-900">
            <tr>
              <th className={cell}>Lugar</th>
              <th className={cell}>Fonte</th>
              <th className={cell}>Situação</th>
              <th className={`${cell} text-right`}>Registros lidos</th>
              <th className={cell}>Última coleta</th>
              <th className={cell}>Próxima automática</th>
              <th className={cell}></th>
            </tr>
          </thead>
          <tbody>
            {places.map((p) => (
                <tr key={`${p.region_id}-${p.source}`} className="border-t border-zinc-200 dark:border-zinc-800">
                  <td className={cell}>{p.region}</td>
                  <td className={`${cell} text-zinc-500`}>{p.source_name}</td>
                  <td className={cell}>{p.active_job_status ? STATUS[p.active_job_status] : STATUS[p.status] ?? p.status}</td>
                  <td className={`${cell} text-right tabular-nums`}>{p.records ? int.format(p.records) : "—"}</td>
                  <td className={cell}>{day(p.last_completed_at)}</td>
                  <td className={cell}>{day(p.next_due_at)}</td>
                  <td className={cell}>
                    {user.role !== "ADMIN" ? null : p.active_job_id ? (
                      <span className="text-xs text-zinc-500">job {p.active_job_id}</span>
                    ) : p.manual_blocked_until ? (
                      <span className="text-xs text-zinc-500">liberado em {day(p.manual_blocked_until)}</span>
                    ) : (
                      <RequestButton regionId={p.region_id} source={p.source} />
                    )}
                  </td>
                </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-3 text-xs text-zinc-500">
        Um lugar fora desta lista só pode ser pesquisado depois que uma fonte que o cubra for avaliada e aprovada (docs/DATA_SOURCES.md).
        {user.role !== "ADMIN" && " Pedir coleta é restrito a administradores."}
      </p>

      {jobs.length > 0 && (
        <>
          <h2 className="mt-8 text-base font-semibold">Últimas execuções</h2>
          <ul className="mt-2 divide-y divide-zinc-200 text-sm dark:divide-zinc-800">
            {jobs.map((j) => (
              <li key={j.id} className="flex flex-wrap justify-between gap-2 py-2">
                <span>
                  #{j.id} · {j.region} · {j.source} · <span className="text-zinc-500">{j.triggered_by}</span>
                </span>
                <span className="text-zinc-500">
                  {STATUS[j.status] ?? j.status}
                  {j.finished_at && ` em ${day(j.finished_at)}`} · {int.format(j.records)} registros ({int.format(j.new_records)} novos)
                  {j.status === "FAILED" && j.last_error && ` · ${j.last_error.slice(0, 80)}`}
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
    </>
  );
}
