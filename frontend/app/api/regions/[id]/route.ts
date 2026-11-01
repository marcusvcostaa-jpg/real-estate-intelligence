import type { NextRequest } from "next/server";
import { forwardGet } from "@/services/proxy-api";

export async function GET(request: NextRequest, ctx: RouteContext<"/api/regions/[id]">) {
  const { id } = await ctx.params;
  if (!/^\d+$/.test(id)) return Response.json({ detail: "invalid id" }, { status: 400 });
  return forwardGet(request, `/regions/${id}`);
}
