import Link from "next/link";

export type Country = { iso2: string; name: string; currency: string };

/** Links to the same page for each country: statistics never mix currencies. */
export function CountrySwitch({ countries, current, path }: { countries: Country[]; current: string; path: string }) {
  if (countries.length < 2) return null;
  return (
    <nav aria-label="País" className="mt-3 flex gap-2 text-sm">
      {countries.map((c) => (
        <Link
          key={c.iso2}
          href={`${path}?country=${c.iso2}`}
          aria-current={c.iso2 === current ? "page" : undefined}
          className={`rounded-md px-3 py-1 ${c.iso2 === current ? "bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900" : "border border-zinc-300 dark:border-zinc-700"}`}
        >
          {c.name} ({c.currency})
        </Link>
      ))}
    </nav>
  );
}

/** The requested country if it has data, else the first one. */
export function pickCountry(countries: Country[], requested: string | string[] | undefined): string {
  const iso = typeof requested === "string" ? requested.toUpperCase() : "";
  return countries.some((c) => c.iso2 === iso) ? iso : (countries[0]?.iso2 ?? "IE");
}
