import { motion } from "framer-motion";
import type { AiInfo, DocKey, ExtractionInfo, Finding } from "../types";
import { listContainer, listItem, sectionIn, still } from "../motion";
import { AlertTriangle, Ban, HelpCircle } from "../icons";
import { useReducedMotion } from "framer-motion";

/** Advisory model output.
 *
 *  Presented apart from the findings, under its own heading, with the caveat
 *  attached to every card rather than stated once at the top. A reviewer who
 *  scrolls straight into a suggestion should still be able to tell that it is
 *  not a check. */
export function AiPanel({
  suggestions, ai, extraction, docNames,
}: {
  suggestions: Finding[];
  ai?: AiInfo;
  extraction?: Record<DocKey, ExtractionInfo>;
  docNames: Record<string, string>;
}) {
  const reduce = useReducedMotion() ?? false;
  const assisted = (["protocol", "report"] as DocKey[]).filter(
    (k) => extraction?.[k]?.source === "ai-assisted",
  );

  if (!ai?.enabled) {
    return (
      <motion.section className="panel" variants={sectionIn} initial="hidden" animate="visible">
        <p className="panel-note">
          <Ban size={13} style={{ verticalAlign: "-2px", marginRight: 6, color: "var(--fg-subtle)" }} />
          AI assistance was not used for this run. Every finding came from a deterministic check.
        </p>
      </motion.section>
    );
  }

  return (
    <motion.div variants={sectionIn} initial="hidden" animate="visible">
      <section className="panel" style={{ marginBottom: "var(--s4)" }}>
        <p className="panel-note">
          <strong>{ai.provider} · {ai.model}</strong> — {ai.boundary}
        </p>
        <div style={{ padding: "var(--s3) var(--s4)", fontSize: 12.5 }}>
          <dl className="manifest-grid" style={{ margin: 0 }}>
            <div className="mf-item">
              <dt>Document structure</dt>
              <dd style={{ fontFamily: "var(--sans)", fontSize: 12.5 }}>
                {assisted.length === 0
                  ? "Both documents were parsed deterministically. The model was not involved in extraction."
                  : assisted.map((k) => (
                      <div key={k}>
                        <b>{docNames[k]}</b>: layout not recognised — located by the model.
                        {" "}{extraction?.[k].quotes_located_in_source} quotes found in the source,
                        {" "}{extraction?.[k].discarded_unverifiable.length} discarded as unverifiable.
                      </div>
                    ))}
              </dd>
            </div>
            {ai.usage && (
              <div className="mf-item">
                <dt>Model usage</dt>
                <dd>
                  {ai.usage.calls} call(s), {ai.usage.prompt_tokens.toLocaleString()} prompt +{" "}
                  {ai.usage.completion_tokens.toLocaleString()} completion tokens
                </dd>
              </div>
            )}
          </dl>
          {ai.notes.length > 0 && (
            <ul style={{ margin: "var(--s3) 0 0", paddingLeft: 18, color: "var(--fg-muted)" }}>
              {ai.notes.map((n, i) => (
                <li key={i} style={{ marginBottom: 3 }}>{n}</li>
              ))}
            </ul>
          )}
        </div>
      </section>

      {ai.suggestions_requested && (
        <>
          <div className="boundary" style={{ marginTop: 0 }}>
            <AlertTriangle />
            <div>
              <strong>These are not findings.</strong>
              <p>
                A model was asked what the rules might have missed. Nothing below was produced by a
                check, and nothing below has been verified beyond confirming that its quotes really
                appear in the documents. Treat each one as a prompt to go and look.
              </p>
            </div>
          </div>

          {suggestions.length === 0 ? (
            <section className="panel">
              <p className="panel-note">The model returned no suggestions that survived the quote check.</p>
            </section>
          ) : (
            <motion.ul
              className="findings"
              variants={still(listContainer, reduce)}
              initial="hidden"
              animate="visible"
            >
              {suggestions.map((s) => (
                <motion.li
                  key={s.id}
                  className="card"
                  data-priority="low"
                  data-source="ai"
                  variants={still(listItem, reduce)}
                >
                  <div className="card-top">
                    <div className="card-meta">
                      <span className="chip chip-ai">
                        <HelpCircle size={11} /> AI suggestion
                      </span>
                      <span className="chip chip-scope">{s.scope}</span>
                      <span className="card-id">{s.id}</span>
                    </div>
                    <p className="card-obs">{s.statement}</p>
                    <div className="uncertainty">
                      <HelpCircle />
                      <div>{s.uncertainty}</div>
                    </div>
                  </div>

                  <div className="evidence">
                    <div className="evidence-in">
                      {[...s.citations]
                        .sort((a, b) => (a.document === "protocol" ? 0 : 1) - (b.document === "protocol" ? 0 : 1))
                        .map((c, i) => (
                          <div className="cite" data-d={c.document} key={i}>
                            <div className="cite-head">
                              <span className="who">{c.document}</span>
                              <span className="loc">{c.locator}</span>
                            </div>
                            <blockquote>{c.quote_display || c.quote}</blockquote>
                            <div className="cite-file">{docNames[c.document]}</div>
                          </div>
                        ))}
                    </div>
                  </div>

                  <p className="action">
                    <b>For the reviewer:</b> {s.reviewer_action}
                  </p>
                </motion.li>
              ))}
            </motion.ul>
          )}
        </>
      )}
    </motion.div>
  );
}
