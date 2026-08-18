import { memo } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import type { Citation, Decision, DecisionRecord, Finding } from "../types";
import { DECISIONS } from "../types";
import { collapse, listItem, snappy, spring, still } from "../motion";
import { Check, Chevron, HelpCircle } from "../icons";

interface Props {
  finding: Finding;
  record: DecisionRecord;
  docNames: Record<string, string>;
  active: boolean;
  open: boolean;
  onToggle: (id: string) => void;
  onDecide: (id: string, decision: Decision) => void;
  onNote: (id: string, note: string) => void;
  onFocus: (id: string) => void;
}

function Evidence({ cite, docNames }: { cite: Citation; docNames: Record<string, string> }) {
  return (
    <div className="cite" data-d={cite.document}>
      <div className="cite-head">
        <span className="who">{cite.document}</span>
        <span className="loc">{cite.locator}</span>
        {cite.note && <span className="note">{cite.note}</span>}
      </div>
      <blockquote>{cite.quote_display || cite.quote}</blockquote>
      <div className="cite-file">{docNames[cite.document] ?? cite.document}</div>
    </div>
  );
}

function FindingCardBase({ finding: f, record, docNames, active, open, onToggle, onDecide, onNote, onFocus }: Props) {
  const reduce = useReducedMotion() ?? false;
  const decided = record.decision !== "open";
  const docs = Array.from(new Set(f.citations.map((c) => c.document))).sort();

  // Always read protocol first, then report: the requirement, then what was
  // recorded against it. Display order only -- the JSON audit record keeps
  // the order the rule emitted.
  const ordered = [...f.citations].sort(
    (a, b) => (a.document === "protocol" ? 0 : 1) - (b.document === "protocol" ? 0 : 1),
  );

  return (
    <motion.li
      layout={!reduce}
      variants={still(listItem, reduce)}
      exit="exit"
      transition={reduce ? { duration: 0 } : spring}
      className="card"
      data-priority={f.review_priority}
      data-decided={decided}
      data-active={active}
      id={f.id}
      onFocusCapture={() => onFocus(f.id)}
      onMouseDown={() => onFocus(f.id)}
    >
      <div className="card-top">
        <div className="card-meta">
          <span className="chip chip-prio" data-p={f.review_priority}>
            {f.review_priority} priority
          </span>
          <span className="chip chip-scope">{f.scope}</span>
          <span className="chip chip-plain">{f.category}</span>
          <span className="card-id">
            {f.id} · {f.rule_id}
          </span>
        </div>

        <p className="card-check">
          <b>Check:</b> {f.rule_title}
        </p>
        <p className="card-obs">{f.observation}</p>

        {f.uncertainty && (
          <div className="uncertainty">
            <HelpCircle />
            <div>
              <b>Where this is not clear cut: </b>
              {f.uncertainty}
            </div>
          </div>
        )}

        <p className="basis">
          <b>Why this is checkable:</b> {f.basis}
        </p>
      </div>

      {f.citations.length > 0 && (
        <>
          <button
            className="evidence-toggle"
            onClick={() => onToggle(f.id)}
            aria-expanded={open}
            aria-controls={`${f.id}-evidence`}
          >
            <motion.span
              className="chev"
              animate={{ rotate: open ? 180 : 0 }}
              transition={reduce ? { duration: 0 } : snappy}
            >
              <Chevron />
            </motion.span>
            {open ? "Hide" : "Show"} the exact text behind this flag
            <span className="docs">
              {docs.map((d) => (
                <span key={d} className="doc-tick" data-d={d}>
                  {d}
                </span>
              ))}
            </span>
          </button>

          <AnimatePresence initial={false}>
            {open && (
              <motion.div
                id={`${f.id}-evidence`}
                className="evidence"
                variants={still(collapse, reduce)}
                initial="closed"
                animate="open"
                exit="closed"
              >
                <div className="evidence-in">
                  {ordered.map((c, i) => (
                    <Evidence key={`${c.document}-${c.locator}-${i}`} cite={c} docNames={docNames} />
                  ))}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </>
      )}

      <p className="action">
        <b>For the reviewer:</b> {f.reviewer_action}
      </p>

      <div className="decision">
        <div className="decision-label">Your decision</div>
        <div className="decision-opts" role="group" aria-label={`Decision for ${f.id}`}>
          {DECISIONS.map((d) => {
            const on = record.decision === d.value;
            return (
              <motion.button
                key={d.value}
                className="opt"
                data-v={d.value}
                aria-pressed={on}
                onClick={() => onDecide(f.id, d.value)}
                whileHover={reduce ? undefined : { y: -1 }}
                whileTap={reduce ? undefined : { scale: 0.97 }}
                transition={snappy}
              >
                {on && d.value !== "open" && <Check size={13} />}
                {d.label}
                <span className="k">{d.hint}</span>
              </motion.button>
            );
          })}
        </div>
        <textarea
          className="note-field"
          rows={1}
          placeholder="Rationale — recorded alongside your decision"
          value={record.note}
          onChange={(e) => onNote(f.id, e.target.value)}
        />
        {record.at && <div className="decided-at">recorded {record.at}</div>}
      </div>
    </motion.li>
  );
}

export const FindingCard = memo(FindingCardBase);
