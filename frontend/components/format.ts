export const eur = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "EUR", maximumFractionDigits: 0 });
export const int = new Intl.NumberFormat("pt-BR");
const moneyFormats = new Map<string, Intl.NumberFormat>();
/** Whole-unit amount in the given ISO 4217 currency (EUR, BRL, ...). */
export const money = (v: number, currency: string) => {
  if (!moneyFormats.has(currency)) {
    moneyFormats.set(currency, new Intl.NumberFormat("pt-BR", { style: "currency", currency, maximumFractionDigits: 0 }));
  }
  return moneyFormats.get(currency)!.format(v);
};
const SYMBOL: Record<string, string> = { EUR: "€", BRL: "R$ " };
export const compactMoney = (v: number, currency: string) => {
  const s = SYMBOL[currency] ?? `${currency} `;
  return v >= 1_000_000 ? `${s}${(v / 1_000_000).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} mi` : `${s}${Math.round(v / 1000)} mil`;
};
export const compactEur = (v: number) => compactMoney(v, "EUR");
export const day = (iso: string | null | undefined) => (iso ? new Date(iso).toLocaleDateString("pt-BR") : "—");
export const monthLabel = (iso: string) =>
  new Date(`${iso}T00:00:00Z`).toLocaleDateString("pt-BR", { month: "short", year: "2-digit", timeZone: "UTC" });

/** Formatters by name, so Server Components can choose one for Client Components (functions
 * cannot cross that boundary). */
export const FORMATS = {
  eur: (v: number) => money(v, "EUR"),
  brl: (v: number) => money(v, "BRL"),
  int: (v: number) => int.format(v),
  compactEur,
  compactBrl: (v: number) => compactMoney(v, "BRL"),
} as const;
export const X_FORMATS = { month: monthLabel, day: (x: string) => day(x) } as const;
export type FormatName = keyof typeof FORMATS;
export type XFormatName = keyof typeof X_FORMATS;
/** Format names for a currency (charts receive names, not functions). */
export const formatsFor = (currency: string): { full: FormatName; compact: FormatName } =>
  currency === "BRL" ? { full: "brl", compact: "compactBrl" } : { full: "eur", compact: "compactEur" };

/** Portuguese label of each country's statistical basis (mirrors BASIS in the analytics API). */
export const BASIS_PT: Record<string, string> = {
  IE: "preço transacionado, valor de mercado pleno, com IVA, residencial",
  BR: "valor declarado no ITBI, compra e venda do imóvel inteiro, residencial",
};
export const PRICE_M2_BASIS_PT =
  "área construída do IPTU (inclui a parte das áreas comuns do condomínio; cadastro do exercício atual)";
/** Top-level areas are counties in Ireland and municipalities in Brazil. */
export const AREA_LABEL: Record<string, string> = { IE: "condado", BR: "município" };
