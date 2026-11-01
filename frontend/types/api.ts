export type UserRole = "ADMIN" | "ANALYST" | "VIEWER";

export type CurrentUser = { id: number; email: string; role: UserRole };

export type Health = { status: "ok" | "degraded"; db: string; redis: string };

export type RegionStatus =
  | "NOT_STARTED"
  | "QUEUED"
  | "IN_PROGRESS"
  | "PARTIALLY_COMPLETED"
  | "COMPLETED"
  | "FAILED"
  | "REQUIRES_REVIEW";

export type RegionProps = {
  id: number;
  name: string;
  level: string;
  status: RegionStatus;
  parent_id: number | null;
  last_searched_at: string | null;
  children: number;
  sales: number | null;
  sales_12m: number | null;
  median_12m: number | null;
};

export type RegionCollection = GeoJSON.FeatureCollection<GeoJSON.Geometry, RegionProps> & {
  median_basis: string;
};

export type RegionDetail = RegionProps & {
  parent_name: string | null;
  boundary_source: string | null;
  properties: number;
  median_basis: string;
  neighbors: string[];
  coverage: {
    source: string;
    source_name: string;
    status: RegionStatus;
    last_completed_at: string | null;
    next_due_at: string | null;
    records: number;
  }[];
};

export type CoverageSummary = {
  regions_by_status: { top_level: Record<string, number>; all: Record<string, number> };
  totals: {
    properties: number;
    transactions: number;
    listings: number;
    active_sources: number;
    last_update: string | null;
    dedup_pending_review: number;
  };
  attributions: string[];
};

export type Kpis = {
  properties: number;
  transactions: number;
  listings: number;
  areas_researched: number;
  areas_total: number;
  regions_researched: number;
  regions_pending: number;
  regions_in_progress: number;
  new_properties_7d: number;
  active_sources: number;
  last_update: string | null;
  review_pending: number;
  jobs_queued: number;
};

export type AreaStats = {
  id: number;
  name: string;
  status: RegionStatus;
  sales: number;
  sales_12m: number;
  median_12m: number | null;
  mean_12m: number | null;
  median_prev_12m: number | null;
  median_change_pct: number | null;
  new_sales_12m: number;
  properties: number;
  repeat_sold_properties: number;
};

export type AreasResponse = { areas: AreaStats[]; basis: string; unavailable: Record<string, string> };

export type TimeSeries = {
  series: { region_id: number; name: string; points: { month: string; sales: number; median: number; provisional: boolean }[] }[];
  basis: string;
};

export type PriceBands = { bands: { min: number; max: number | null; sales: number }[]; basis: string };

export type PropertyRow = {
  public_id: string;
  address_display: string | null;
  postal_code: string | null;
  region: string;
  sales: number;
  first_sale_date: string;
  last_sale_date: string;
  last_sale_price: number;
  currency: string;
  last_full_market: boolean | null;
  last_vat_exclusive: boolean | null;
  last_is_new: boolean;
};

export type PropertyPage = { items: PropertyRow[]; next_cursor: string | null; price_kind: string };

export type PropertyDetail = {
  public_id: string;
  address_display: string | null;
  postal_code: string | null;
  property_type: string;
  category: string;
  region: string | null;
  pending_reviews: number;
  price_kind: string;
  sales: {
    id: number;
    transaction_date: string;
    price: number;
    currency: string;
    is_full_market_price: boolean | null;
    vat_exclusive: boolean | null;
    address_original: string | null;
    postal_code: string | null;
    description_original: string | null;
    source: string;
  }[];
};

export type ReviewItem = {
  id: number;
  score: number;
  vetoes: string[];
  method: string;
  decision: string;
  sale_address: string | null;
  sale_date: string;
  sale_price: number;
  sale_eircode: string | null;
  candidate_address: string | null;
  candidate_eircode: string | null;
  candidate_public_id: string;
  candidate_sales: number;
  region: string | null;
};

export type ReviewQueue = { items: ReviewItem[]; total: number };
