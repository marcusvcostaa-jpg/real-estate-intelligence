export const eur = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "EUR", maximumFractionDigits: 0 });
export const int = new Intl.NumberFormat("pt-BR");
export const compactEur = (v: number) =>
  v >= 1_000_000 ? `€${(v / 1_000_000).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} mi` : `€${Math.round(v / 1000)} mil`;
export const day = (iso: string | null | undefined) => (iso ? new Date(iso).toLocaleDateString("pt-BR") : "—");
export const monthLabel = (iso: string) =>
  new Date(`${iso}T00:00:00Z`).toLocaleDateString("pt-BR", { month: "short", year: "2-digit", timeZone: "UTC" });

/** Formatters by name, so Server Components can choose one for Client Components (functions
 * cannot cross that boundary). */
export const FORMATS = {
  eur: (v: number) => eur.format(v),
  int: (v: number) => int.format(v),
  compactEur,
} as const;
export const X_FORMATS = { month: monthLabel, day: (x: string) => day(x) } as const;
export type FormatName = keyof typeof FORMATS;
export type XFormatName = keyof typeof X_FORMATS;

/** Portuguese label for the API's statistical basis. */
export const BASIS_PT = "preço transacionado, valor de mercado pleno, com IVA";
