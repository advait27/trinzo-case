import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import type { Payload } from "./types";
import "./styles.css";

/* The data is embedded in the page by render.py as a JSON script block --
   no fetch, because the sheet has to work from a file:// path with no
   server and no network. */
function readPayload(): Payload | null {
  const el = document.getElementById("review-data");
  if (!el?.textContent) return null;
  try {
    return JSON.parse(el.textContent) as Payload;
  } catch (err) {
    console.error("protocolqc: embedded review data is not valid JSON", err);
    return null;
  }
}

/* Theme is applied before React mounts so the first paint is already correct. */
try {
  const saved = localStorage.getItem("protocolqc:theme");
  if (saved === "dark" || saved === "light") document.documentElement.dataset.theme = saved;
  else if (window.matchMedia("(prefers-color-scheme: dark)").matches)
    document.documentElement.dataset.theme = "dark";
} catch {
  /* file:// origins may refuse storage; fall through to the light default */
}

const mount = document.getElementById("root")!;
const payload = readPayload();

if (!payload) {
  mount.innerHTML =
    '<div style="max-width:640px;margin:80px auto;font:15px/1.6 system-ui;padding:0 24px">' +
    "<h1 style='font-size:18px'>This review sheet could not load its data</h1>" +
    "<p>The embedded findings block is missing or malformed. Re-run protocolqc to regenerate the file. " +
    "The JSON audit record written alongside it is unaffected.</p></div>";
} else {
  createRoot(mount).render(
    <StrictMode>
      <App payload={payload} />
    </StrictMode>,
  );
}
