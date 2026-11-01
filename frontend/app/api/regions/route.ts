import type { NextRequest } from "next/server";
import { forwardGet } from "@/services/proxy-api";

export async function GET(request: NextRequest) {
  const parentId = request.nextUrl.searchParams.get("parent_id");
  if (parentId !== null && !/^\d+$/.test(parentId)) {
    return Response.json({ detail: "invalid parent_id" }, { status: 400 });
  }
  return forwardGet(request, parentId ? `/regions?parent_id=${parentId}` : "/regions");
}
