import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, LayoutGroup, motion, useReducedMotion } from "framer-motion";
import type { Decision, DecisionRecord, Payload, Priority } from "./types";
import { FindingCard } from "./components/FindingCard";
import { ChecksTable, LimitsTable } from "./components/Tables";
import { ManifestPanel } from "./components/Manifest";
import { PillGroup, SearchBox } from "./components/Toolbar";
import { AiPanel } from "./components/AiPanel";
import { listContainer, sectionIn, smooth, spring, still } from "./motion";
import {
  AlertTriangle, CheckCircle, Download, FileDiff, Moon, Printer, ShieldCheck, Sun, Upload,
} from "./icons";

const PRIORITY_COLOR: Record<Priority, string> = {
  high: "var(--hi)",
  medium: "var(--med)",
  low: "var(--lo)",
};

const EMPTY: DecisionRecord = { decision: "open", note: "", at: null };

function storageKey(runAt: string) {
  return `protocolqc:${runAt}`;
}

/** localStorage is not guaranteed on a file:// origin. If it is unavailable
    the sheet still works for the whole session; it just cannot remember
    across a reload, and says so rather than throwing on every keystroke. */
function loadDecisions(key: string): { data: Record<string, DecisionRecord>; ok: boolean } {
  try {
    return { data: JSON.parse(localStorage.getItem(key) || "{}"), ok: true };
  } catch {
    return { data: {}, ok: false };
  }
}

export default function App({ payload }: { payload: Payload }) {
  const { manifest, findings, rules_run, not_checked } = payload;

  // This sheet is one self-contained file. It is opened straight off disk at
  // least as often as it is served, and it gets emailed around. A link to the
  // upload page is only correct when that page is actually reachable, which is
  // exactly when the server handed us this sheet at /r/<id>. Matching that path
  // rather than merely checking for http: means a copy dropped on some other
  // static host does not grow a dead "New review" button.
  const servedByApp = /^\/r\/[0-9a-f]{12}\/?$/.test(window.location.pathname);
  const suggestions = payload.ai_suggestions ?? [];
  const reduce = useReducedMotion() ?? false;
  const key = storageKey(manifest.run_at_utc);

  const [decisions, setDecisions] = useState<Record<string, DecisionRecord>>(() => loadDecisions(key).data);
  const [storageOk, setStorageOk] = useState(true);
  const [tab, setTab] = useState<"findings" | "checks" | "limits" | "ai">("findings");
  const [priority, setPriority] = useState("all");
  const [state, setState] = useState("all");
  const [scope, setScope] = useState("all");
  const [query, setQuery] = useState("");
  // Evidence starts open: the quoted text is the reason to trust a flag, so it
  // should not be a click away. Collapse-all is there for scanning.
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set(findings.map((f) => f.id)));
  const [activeId, setActiveId] = useState<string | null>(findings[0]?.id ?? null);
  const [theme, setTheme] = useState<"light" | "dark">(
    () => (document.documentElement.dataset.theme as "light" | "dark") || "light",
  );
  const searchRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem("protocolqc:theme", theme);
    } catch { /* non-persistent origin */ }
  }, [theme]);

  const persist = useCallback(
    (next: Record<string, DecisionRecord>) => {
      setDecisions(next);
      try {
        localStorage.setItem(key, JSON.stringify(next));
      } catch {
        setStorageOk(false);
      }
    },
    [key],
  );

  const rec = useCallback((id: string) => decisions[id] ?? EMPTY, [decisions]);

  const decide = useCallback(
    (id: string, decision: Decision) => {
      const prev = decisions[id] ?? EMPTY;
      persist({
        ...decisions,
        [id]: {
          ...prev,
          decision,
          at: decision === "open" ? null : new Date().toISOString().replace("T", " ").slice(0, 19) + " UTC",
        },
      });
    },
    [decisions, persist],
  );

  const setNote = useCallback(
    (id: string, note: string) => {
      const prev = decisions[id] ?? EMPTY;
      persist({ ...decisions, [id]: { ...prev, note } });
    },
    [decisions, persist],
  );

  const toggleEvidence = useCallback((id: string) => {
    setExpanded((s) => {
      const next = new Set(s);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }, []);

  const counts = useMemo(() => {
    const c = { high: 0, medium: 0, low: 0 };
    findings.forEach((f) => (c[f.review_priority] += 1));
    return c;
  }, [findings]);

  const reviewed = findings.filter((f) => rec(f.id).decision !== "open").length;
  const scopes = useMemo(
    () => Array.from(new Set(findings.map((f) => f.scope))).sort(),
    [findings],
  );

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return findings.filter((f) => {
      if (priority !== "all" && f.review_priority !== priority) return false;
      if (scope !== "all" && f.scope !== scope) return false;
      const d = rec(f.id).decision;
      if (state === "open" && d !== "open") return false;
      if (state === "done" && d === "open") return false;
      if (!q) return true;
      const hay = [
        f.id, f.rule_id, f.rule_title, f.observation, f.basis, f.reviewer_action,
        f.uncertainty, f.scope, f.category,
        ...f.citations.map((c) => c.quote_display || c.quote),
      ].join(" ").toLowerCase();
      return hay.includes(q);
    });
  }, [findings, priority, scope, state, query, rec]);

  /* Keyboard: j/k to move, 1-4 to decide, e for evidence, / to search. */
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const el = e.target as HTMLElement;
      const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName);
      if (e.key === "/" && !typing) {
        e.preventDefault();
        searchRef.current?.focus();
        return;
      }
      if (typing || e.metaKey || e.ctrlKey || e.altKey) return;
      if (tab !== "findings" || visible.length === 0) return;

      const i = Math.max(0, visible.findIndex((f) => f.id === activeId));
      const focus = (n: number) => {
        const target = visible[Math.min(visible.length - 1, Math.max(0, n))];
        if (!target) return;
        setActiveId(target.id);
        document.getElementById(target.id)?.scrollIntoView({
          behavior: reduce ? "auto" : "smooth",
          block: "center",
        });
      };
      if (e.key === "j") { e.preventDefault(); focus(i + 1); }
      else if (e.key === "k") { e.preventDefault(); focus(i - 1); }
      else if (e.key === "e" && activeId) { e.preventDefault(); toggleEvidence(activeId); }
      else if (["1", "2", "3", "4"].includes(e.key) && activeId) {
        e.preventDefault();
        decide(activeId, (["open", "confirmed", "not-an-issue", "more-info"] as Decision[])[Number(e.key) - 1]);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [visible, activeId, tab, decide, toggleEvidence, reduce]);

  function exportDecisions() {
    const payloadOut = {
      run: manifest.run_at_utc,
      tool: `${manifest.tool} ${manifest.tool_version}`,
      ruleset: manifest.ruleset_version,
      documents: manifest.documents,
      exported_at: new Date().toISOString(),
      decisions: Object.fromEntries(findings.map((f) => [f.id, rec(f.id)])),
    };
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([JSON.stringify(payloadOut, null, 2)], { type: "application/json" }));
    a.download = "reviewer-decisions.json";
    a.click();
    URL.revokeObjectURL(a.href);
  }

  const docNames = {
    protocol: manifest.documents.protocol.name,
    report: manifest.documents.report.name,
  };
  const pct = findings.length ? reviewed / findings.length : 1;

  return (
    <>
      <a className="skip" href="#main">Skip to findings</a>

      <header className="masthead">
        <div className="masthead-in">
          <div className="brand">
            <span className="brand-mark"><FileDiff /></span>
            <div style={{ minWidth: 0 }}>
              <h1>Protocol-to-report review</h1>
              <p>{docNames.protocol} vs {docNames.report}</p>
            </div>
          </div>

          <div className="masthead-actions">
            {findings.length > 0 && (
              <div className="progress-cluster">
                <span className="progress-text"><b>{reviewed}</b> of <b>{findings.length}</b> reviewed</span>
                <div className="progress-rail" role="progressbar" aria-valuenow={reviewed} aria-valuemin={0} aria-valuemax={findings.length}>
                  <motion.div
                    className="progress-fill"
                    initial={false}
                    animate={{ scaleX: pct }}
                    transition={reduce ? { duration: 0 } : spring}
                    style={{ width: "100%" }}
                  />
                </div>
              </div>
            )}
            <button className="icon-btn" onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
                    aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`} title="Toggle theme">
              {theme === "dark" ? <Sun /> : <Moon />}
            </button>
            <button className="icon-btn" onClick={() => window.print()} aria-label="Print this review sheet" title="Print">
              <Printer />
            </button>
            <button className="btn btn-primary" onClick={exportDecisions}>
              <Download /> Export decisions
            </button>
            {servedByApp && (
              <a className="btn" href="/"
                 title="Upload a different protocol and report">
                <Upload /> New review
              </a>
            )}
          </div>
        </div>
      </header>

      <div className="shell">
        <div className="boundary" role="note">
          <ShieldCheck />
          <div>
            <strong>This is not a pass/fail decision.</strong>
            <p>{manifest.boundary}</p>
          </div>
        </div>

        {!storageOk && (
          <div className="boundary" role="status" style={{ borderLeftColor: "var(--lo)", background: "var(--lo-soft)" }}>
            <AlertTriangle />
            <div>
              <strong>Decisions cannot be saved in this browser</strong>
              <p>They are held for this session only. Use “Export decisions” before closing the tab.</p>
            </div>
          </div>
        )}

        {findings.length > 0 && (
          <motion.div className="stat-row" variants={sectionIn} initial="hidden" animate="visible">
            {(["high", "medium", "low"] as Priority[]).map((p) => (
              <div className="stat" key={p}>
                <span className="stat-dot" style={{ background: PRIORITY_COLOR[p] }} />
                <div>
                  <div className="stat-n">{counts[p]}</div>
                  <div className="stat-l">{p} priority</div>
                </div>
              </div>
            ))}
            <div className="stat">
              <span className="stat-dot" style={{ background: "var(--green)" }} />
              <div>
                <div className="stat-n">{reviewed}/{findings.length}</div>
                <div className="stat-l">decisions recorded</div>
              </div>
            </div>
          </motion.div>
        )}

        <ManifestPanel manifest={manifest} />

        <LayoutGroup>
          <div className="tabs" role="tablist">
            {([
              ["findings", "Findings", findings.length],
              ["checks", "Checks that ran", rules_run.length],
              ["limits", "Not checked", not_checked.length],
              ["ai", manifest.ai?.enabled ? "AI assistance" : "AI (off)", suggestions.length],
            ] as const).map(([id, label, n]) => (
              <button key={id} className="tab" role="tab" aria-selected={tab === id} onClick={() => setTab(id)}>
                {label}<span className="count">{n}</span>
                {tab === id &&
                  (reduce ? <span className="tab-ink" /> : <motion.span className="tab-ink" layoutId="tab-ink" transition={spring} />)}
              </button>
            ))}
          </div>
        </LayoutGroup>

        <main id="main">
          <AnimatePresence mode="wait">
            {tab === "findings" && (
              <motion.div key="findings" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={smooth}>
                {findings.length === 0 ? (
                  <div className="clean">
                    <div className="clean-mark"><CheckCircle /></div>
                    <h3>No differences were raised</h3>
                    <p>
                      Every check ran against these two documents and none of them had anything to
                      report. That is not the same as a pass.
                    </p>
                    <div className="caveat">
                      <AlertTriangle />
                      <div>
                        An empty result means <b>these checks</b> found nothing. Open{" "}
                        <b>Checks that ran</b> to see exactly what was compared, and{" "}
                        <b>Not checked</b> for what this tool cannot see at all. Disposition remains
                        the reviewer’s.
                      </div>
                    </div>
                  </div>
                ) : (
                  <>
                    <div className="toolbar">
                      <SearchBox value={query} onChange={setQuery} inputRef={searchRef} />
                      <div className="filters">
                        <PillGroup
                          groupId="prio" label="Filter by priority" value={priority} onChange={setPriority}
                          options={[
                            { value: "all", label: "All", count: findings.length },
                            { value: "high", label: "High", count: counts.high },
                            { value: "medium", label: "Medium", count: counts.medium },
                            { value: "low", label: "Low", count: counts.low },
                          ]}
                        />
                        <PillGroup
                          groupId="state" label="Filter by review state" value={state} onChange={setState}
                          options={[
                            { value: "all", label: "Any state" },
                            { value: "open", label: "To review", count: findings.length - reviewed },
                            { value: "done", label: "Decided", count: reviewed },
                          ]}
                        />
                        <PillGroup
                          groupId="scope" label="Filter by scope" value={scope} onChange={setScope}
                          options={[{ value: "all", label: "All scopes" }, ...scopes.map((s) => ({ value: s, label: s }))]}
                        />
                      </div>
                      <button
                        className="btn"
                        onClick={() =>
                          setExpanded(expanded.size ? new Set() : new Set(findings.map((f) => f.id)))
                        }
                      >
                        {expanded.size ? "Collapse evidence" : "Expand evidence"}
                      </button>
                    </div>

                    <motion.ul
                      className="findings"
                      variants={still(listContainer, reduce)}
                      initial="hidden"
                      animate="visible"
                    >
                      <AnimatePresence mode="popLayout" initial={false}>
                        {visible.map((f) => (
                          <FindingCard
                            key={f.id}
                            finding={f}
                            record={rec(f.id)}
                            docNames={docNames}
                            active={activeId === f.id}
                            open={expanded.has(f.id)}
                            onToggle={toggleEvidence}
                            onDecide={decide}
                            onNote={setNote}
                            onFocus={setActiveId}
                          />
                        ))}
                      </AnimatePresence>
                    </motion.ul>

                    {visible.length === 0 && (
                      <motion.p className="no-match" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                        No findings match these filters.
                      </motion.p>
                    )}
                  </>
                )}
              </motion.div>
            )}

            {tab === "checks" && (
              <motion.div key="checks" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={smooth}>
                <ChecksTable rules={rules_run} />
              </motion.div>
            )}

            {tab === "limits" && (
              <motion.div key="limits" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={smooth}>
                <LimitsTable limits={not_checked} />
              </motion.div>
            )}

            {tab === "ai" && (
              <motion.div key="ai" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={smooth}>
                <AiPanel
                  suggestions={suggestions}
                  ai={manifest.ai}
                  extraction={manifest.extraction}
                  docNames={docNames}
                />
              </motion.div>
            )}
          </AnimatePresence>
        </main>

        <footer className="foot">
          <p>
            Generated by {manifest.tool} {manifest.tool_version}. Prototype for demonstration — not
            qualified software, and not a validated record.
          </p>
          <p>Decisions are stored in this browser only. Export them to keep a copy.</p>
          {!servedByApp && (
            <p>
              To review your own protocol and report, start the upload app with{" "}
              <code>python -m protocolqc.server</code> and open the address it prints.
            </p>
          )}
          <div className="shortcuts">
            <span><kbd>j</kbd><kbd>k</kbd> move</span>
            <span><kbd>1</kbd>–<kbd>4</kbd> record a decision</span>
            <span><kbd>e</kbd> evidence</span>
            <span><kbd>/</kbd> search</span>
          </div>
        </footer>
      </div>
    </>
  );
}
