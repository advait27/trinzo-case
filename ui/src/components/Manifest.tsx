import { useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import type { Manifest as M } from "../types";
import { collapse, snappy, still } from "../motion";
import { Ban, Check, Chevron } from "../icons";

/** The audit header: which files were read, their hashes, and the result of
    the citation-verification gate. Collapsed by default -- a reviewer needs it
    available and traceable, not in the way of the findings. */
export function ManifestPanel({ manifest }: { manifest: M }) {
  const reduce = useReducedMotion() ?? false;
  const [open, setOpen] = useState(false);
  const v = manifest.citation_verification;

  return (
    <section className="manifest">
      <button className="manifest-head" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        Run record
        {v.passed ? (
          <span className="verified">
            <Check size={12} />
            {v.citations_checked} citations / {v.spans_checked} spans re-read from source — all matched
          </span>
        ) : (
          <span className="verified" style={{ color: "var(--red)", background: "var(--hi-soft)" }}>
            <Ban size={12} /> citation verification failed
          </span>
        )}
        <motion.span className="chev" animate={{ rotate: open ? 180 : 0 }} transition={reduce ? { duration: 0 } : snappy}>
          <Chevron />
        </motion.span>
      </button>

      <AnimatePresence initial={false}>
        {open && (
          <motion.div variants={still(collapse, reduce)} initial="closed" animate="open" exit="closed" style={{ overflow: "hidden" }}>
            <div className="manifest-body">
              <div className="manifest-grid">
                {(["protocol", "report"] as const).map((k) => (
                  <dl className="mf-item" key={k}>
                    <dt>{k} document</dt>
                    <dd>
                      <span className="name">{manifest.documents[k].name}</span>
                      SHA-256 {manifest.documents[k].file_sha256 ?? "n/a"}
                    </dd>
                  </dl>
                ))}
                <dl className="mf-item">
                  <dt>Run (UTC)</dt>
                  <dd>{manifest.run_at_utc}</dd>
                </dl>
                <dl className="mf-item">
                  <dt>Tool / ruleset</dt>
                  <dd>
                    {manifest.tool} {manifest.tool_version} / ruleset {manifest.ruleset_version}
                  </dd>
                </dl>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  );
}
