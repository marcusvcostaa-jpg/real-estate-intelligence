import Link from "next/link";
import { Suspense } from "react";
import { logout } from "@/app/actions/auth";
import { getCurrentUser } from "@/services/api";

const NAV = [
  { href: "/", label: "Início" },
  { href: "/map", label: "Mapa" },
  { href: "/analytics", label: "Análises" },
  { href: "/properties", label: "Imóveis" },
  { href: "/review", label: "Revisão" },
];

export default function DashboardLayout({ children }: LayoutProps<"/">) {
  return (
    <div className="flex min-h-full flex-1 flex-col">
      <header className="border-b border-zinc-200 dark:border-zinc-800">
        <div className="mx-auto flex w-full max-w-7xl flex-wrap items-center justify-between gap-3 px-4 py-3">
          <nav className="flex flex-wrap items-center gap-4 text-sm" aria-label="Principal">
            <span className="font-semibold tracking-tight">Real Estate Intelligence</span>
            {NAV.map((item) => (
              <Link key={item.href} href={item.href} className="text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100">
                {item.label}
              </Link>
            ))}
          </nav>
          <Suspense fallback={<span className="text-xs text-zinc-500">…</span>}>
            <UserMenu />
          </Suspense>
        </div>
      </header>
      {children}
    </div>
  );
}

async function UserMenu() {
  const user = await getCurrentUser();
  return (
    <form action={logout} className="flex items-center gap-3 text-xs text-zinc-500">
      <span>
        {user.email} · {user.role}
      </span>
      <button type="submit" className="underline hover:text-zinc-900 dark:hover:text-zinc-100">
        Sair
      </button>
    </form>
  );
}
