import { Suspense } from "react";
import { logout } from "@/app/actions/auth";
import { getCurrentUser, getHealth } from "@/services/api";

export default function Home() {
  return (
    <main className="mx-auto w-full max-w-4xl flex-1 px-4 py-8">
      <h1 className="text-xl font-semibold tracking-tight">Real Estate Intelligence</h1>
      <p className="mt-1 text-sm text-zinc-500">
        Fase 2 — fundação. O dashboard com dados reais chega nas próximas fases.
      </p>
      <Suspense fallback={<p className="mt-6 text-sm text-zinc-500">Carregando…</p>}>
        <SessionPanel />
      </Suspense>
    </main>
  );
}

async function SessionPanel() {
  const [user, health] = await Promise.all([getCurrentUser(), getHealth()]);
  const status = (value?: string) => (value === "ok" ? "ok" : "indisponível");

  return (
    <section className="mt-6 rounded-lg border border-zinc-200 p-4 text-sm dark:border-zinc-800">
      <div className="flex items-center justify-between gap-4">
        <p>
          Conectado como <strong>{user.email}</strong> ({user.role})
        </p>
        <form action={logout}>
          <button type="submit" className="text-zinc-500 underline hover:text-zinc-900 dark:hover:text-zinc-100">
            Sair
          </button>
        </form>
      </div>
      <dl className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-3">
        <dt className="text-zinc-500">API</dt>
        <dd className="sm:col-span-2">{health ? health.status : "indisponível"}</dd>
        <dt className="text-zinc-500">Banco de dados</dt>
        <dd className="sm:col-span-2">{status(health?.db)}</dd>
        <dt className="text-zinc-500">Redis</dt>
        <dd className="sm:col-span-2">{status(health?.redis)}</dd>
      </dl>
    </section>
  );
}
