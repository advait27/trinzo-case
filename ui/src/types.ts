/** Shape of the JSON that protocolqc embeds in the page. Mirrors render.to_json. */

export type Priority = "high" | "medium" | "low";
export type DocKey = "protocol" | "report";
export type Decision = "open" | "confirmed" | "not-an-issue" | "more-info";

export interface Span {
  doc: DocKey;
  page: number;
  line: number;
  start: number;
  end: number;
  text: string;
}

export interface Citation {
  document: DocKey;
  note: string;
  locator: string;
  quote: string;
  quote_display: string;
  display_differs_from_source: boolean;
  spans: Span[];
}

export interface Finding {
  id: string;
  rule_id: string;
  rule_title: string;
  category: string;
  review_priority: Priority;
  scope: string;
  observation: string;
  basis: string;
  reviewer_action: string;
  uncertainty: string;
  /** "rule" for a deterministic check, "ai-suggested" for advisory model output. */
  source?: "rule" | "ai-suggested";
  citations: Citation[];
}

export interface RuleOutcome {
  rule_id: string;
  title: string;
  category: string;
  question: string;
  fired: number;
  status: "findings" | "no-finding" | "not-applicable";
  detail: string;
}

export interface Limit {
  scope: string;
  item: string;
  reason: string;
  citation: Citation | null;
}

export interface DocumentMeta {
  name: string;
  path: string | null;
  file_sha256: string | null;
  extracted_text_sha256: string;
  pages: number;
}

export interface Manifest {
  tool: string;
  tool_version: string;
  ruleset_version: string;
  run_at_utc: string;
  documents: Record<DocKey, DocumentMeta>;
  citation_verification: {
    citations_checked: number;
    spans_checked: number;
    failures: string[];
    passed: boolean;
  };
  boundary: string;
}

export interface AiInfo {
  enabled: boolean;
  model: string | null;
  provider: string | null;
  suggestions_requested: boolean;
  suggestions_kept: number;
  notes: string[];
  boundary: string;
  usage: { calls: number; prompt_tokens: number; completion_tokens: number } | null;
}

export interface ExtractionInfo {
  source: "deterministic" | "ai-assisted";
  model: string | null;
  reason: string;
  tests_found: number;
  quotes_located_in_source: number;
  line_hints_corrected: number;
  discarded_unverifiable: string[];
}

export interface Payload {
  manifest: Manifest & {
    ai?: AiInfo;
    extraction?: Record<DocKey, ExtractionInfo>;
  };
  findings: Finding[];
  /** Advisory model output. Deliberately a separate list so nothing can treat
   *  a suggestion as a check result. */
  ai_suggestions?: Finding[];
  rules_run: RuleOutcome[];
  not_checked: Limit[];
}

export interface DecisionRecord {
  decision: Decision;
  note: string;
  at: string | null;
}

export const DECISIONS: { value: Decision; label: string; hint: string }[] = [
  { value: "open", label: "Not yet reviewed", hint: "1" },
  { value: "confirmed", label: "Confirmed issue", hint: "2" },
  { value: "not-an-issue", label: "Not an issue", hint: "3" },
  { value: "more-info", label: "Needs more information", hint: "4" },
];
