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
