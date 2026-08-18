import { motion } from "framer-motion";
import type { Limit, RuleOutcome } from "../types";
import { sectionIn } from "../motion";
import { AlertTriangle, Ban, Check, Minus } from "../icons";

const STATUS_ICON = {
  "no-finding": <Check size={12} />,
  findings: <AlertTriangle size={12} />,
  "not-applicable": <Minus size={12} />,
} as const;

/** Every rule that ran, including the ones that found nothing. This is the
    panel that lets a reviewer tell "checked, nothing to raise" apart from
    "never looked" -- without it an empty findings list means nothing. */
export function ChecksTable({ rules }: { rules: RuleOutcome[] }) {
  return (
    <motion.section className="panel" variants={sectionIn} initial="hidden" animate="visible">
      <p className="panel-note">
        Every check this run performed, and what it concluded. Listed so that silence can be told
        apart from the absence of a check.
      </p>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th scope="col">Rule</th>
              <th scope="col">Check</th>
              <th scope="col">Question it asks</th>
              <th scope="col">Outcome</th>
              <th scope="col">Detail</th>
            </tr>
          </thead>
          <tbody>
            {rules.map((r) => (
              <tr key={r.rule_id}>
                <td className="rule-id">{r.rule_id}</td>
                <td>{r.title}</td>
                <td style={{ color: "var(--fg-muted)" }}>{r.question}</td>
                <td>
                  <span className="status" data-s={r.status}>
                    {STATUS_ICON[r.status]}
                    {r.status === "findings" ? `${r.fired} raised` : r.status.replace("-", " ")}
                  </span>
                </td>
                <td style={{ color: "var(--fg-muted)" }}>{r.detail}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </motion.section>
  );
}

/** Published blind spots. A clean run that does not say what it could not
    check reads as "everything is fine", which is not what it means. */
export function LimitsTable({ limits }: { limits: Limit[] }) {
  return (
    <motion.section className="panel" variants={sectionIn} initial="hidden" animate="visible">
      <p className="panel-note">
        <Ban size={13} style={{ verticalAlign: "-2px", marginRight: 6, color: "var(--med)" }} />
        An empty result is not a pass. These are the things this run did <b>not</b> check, and they
        still need a human.
      </p>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th scope="col">Scope</th>
              <th scope="col">Item</th>
              <th scope="col">Why it is outside this tool</th>
            </tr>
          </thead>
          <tbody>
            {limits.map((l, i) => (
              <tr key={`${l.scope}-${i}`}>
                <td>
                  <span className="chip chip-plain">{l.scope}</span>
                </td>
                <td>{l.item}</td>
                <td style={{ color: "var(--fg-muted)" }}>{l.reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </motion.section>
  );
}
