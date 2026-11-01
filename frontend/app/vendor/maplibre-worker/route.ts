import { readFile } from "node:fs/promises";
import path from "node:path";

// MapLibre v6 loads its web worker relative to its own script URL, which the bundler does not
// serve. The worker file (self-contained, BSD-3) is served from the installed package instead.
const WORKER = path.join(process.cwd(), "node_modules/maplibre-gl/dist/maplibre-gl-worker.mjs");

export async function GET() {
  return new Response(await readFile(WORKER), {
    headers: {
      "content-type": "text/javascript; charset=utf-8",
      "cache-control": "public, max-age=86400",
    },
  });
}
