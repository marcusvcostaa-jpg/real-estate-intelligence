export type UserRole = "ADMIN" | "ANALYST" | "VIEWER";

export type CurrentUser = { id: number; email: string; role: UserRole };

export type Health = { status: "ok" | "degraded"; db: string; redis: string };
