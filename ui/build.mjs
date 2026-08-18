/* Bundle the review sheet into two committed assets that render.py inlines.
   Everything is bundled -- React, Framer Motion, the app, the CSS -- because
   the published page must be a single file that opens from disk with no
   network access and no CDN. */

import { build, context } from "esbuild";
import { mkdirSync, statSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const outdir = resolve(here, "../protocolqc/assets");
mkdirSync(outdir, { recursive: true });

const options = {
  entryPoints: [resolve(here, "src/main.tsx")],
  bundle: true,
  format: "iife",
  target: ["es2020"],
  minify: true,
  legalComments: "none",
  jsx: "automatic",
  define: { "process.env.NODE_ENV": '"production"' },
  outdir,
  entryNames: "review-app",
  loader: { ".tsx": "tsx", ".ts": "ts" },
  logLevel: "info",
};

const kb = (p) => (statSync(p).size / 1024).toFixed(1) + " KB";

if (process.argv.includes("--watch")) {
  const ctx = await context(options);
  await ctx.watch();
  console.log("watching…");
} else {
  await build(options);
  console.log(`review-app.js  ${kb(resolve(outdir, "review-app.js"))}`);
  console.log(`review-app.css ${kb(resolve(outdir, "review-app.css"))}`);
}
