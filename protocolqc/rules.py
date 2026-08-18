"""The checks.

Each rule is a small, independent function. It receives both parsed documents,
returns Findings, and always records an outcome -- including "I ran and found
nothing", which is deliberately different from "I never looked".

Two conventions hold throughout and are the reason this tool is safe to put in
front of a reviewer:

1. Nothing here decides pass or fail. Findings state what each document says
   and how the two differ. The verb is always "the report records" / "the
   protocol requires", never "the test failed".
2. Reported values are compared against the PROTOCOL's acceptance criterion,
   never against the criterion the report restates for itself. Comparing a
   report to its own restated criterion is exactly how a weakened criterion
   slips through unnoticed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

from . import extract as ex
from .model import Citation, Finding, RuleOutcome, normalise, squash
from .normalize import (
    Qualitative,
    Range,
    Threshold,
    parse_criterion,
    parse_int,
    parse_measurements,
    quantified_qualifiers,
    temperatures,
    worst_case,
)

RULESET_VERSION = "0.3.0"

# Equipment-looking tokens that are actually standards references.
STANDARDS = ("ISO", "USP", "IEC", "EN", "ASTM", "BS")


@dataclass
class Ctx:
    protocol: ex.ParsedDoc
    report: ex.ParsedDoc
    findings: List[Finding]

    def fired(self, rule_id: str, scope: Optional[str] = None) -> List[Finding]:
        return [
            f
            for f in self.findings
            if f.rule_id == rule_id and (scope is None or f.scope == scope)
        ]

    def shared_tests(self) -> List[str]:
        rep = self.report.rows()
        return [t for t in self.protocol.test_ids() if t in rep]


@dataclass
class Rule:
    id: str
    title: str
    category: str
    question: str
    fn: Callable[[Ctx], Tuple[List[Finding], str, str]]


REGISTRY: List[Rule] = []


def rule(id: str, title: str, category: str, question: str):
    def deco(fn):
        REGISTRY.append(Rule(id, title, category, question, fn))
        return fn

    return deco


def _f(rule: Rule, scope: str, priority: str, statement: str, basis: str,
       action: str, citations: List[Optional[Citation]], uncertainty: str = "") -> Finding:
    return Finding(
        id="",  # assigned by run_rules once ordering is known
        rule_id=rule.id,
        rule_title=rule.title,
        category=rule.category,
        priority=priority,
        scope=scope,
        statement=statement,
        basis=basis,
        reviewer_action=action,
        citations=[c for c in citations if c and c.spans],
        uncertainty=uncertainty,
    )


def _me(fn) -> Rule:
    """The Rule object for the currently executing rule function."""
    return next(r for r in REGISTRY if r.fn is fn)


# =====================================================================
# Document identity and control
# =====================================================================

@rule("R-01", "Report cites the current protocol version", "identity",
      "Does the version of the protocol named by the report match the protocol supplied?")
def r01(ctx: Ctx):
    me = _me(r01)
    ref_id, ref_ver, field = ex.protocol_reference(ctx.report)
    actual = ex.version(ctx.protocol)
    if field is None or ref_ver is None or actual is None:
        return [], "not-applicable", "Report does not state a protocol version."
    if ref_ver == actual:
        return [], "no-finding", f"Report cites version {ref_ver}; protocol is version {actual}."

    reporting = ctx.protocol.cite_phrase(r"must reference this", "Section 4, Reporting")
    ver_field = ctx.protocol.field("Version")
    return (
        [
            _f(
                me,
                "document",
                "high",
                f"The report states that it verifies protocol version {ref_ver}. "
                f"The protocol supplied is version {actual}.",
                "The protocol requires the verification report to reference this protocol version.",
                "Confirm which protocol version the testing was actually run against, and whether "
                "version " + actual + " changed anything the report relies on.",
                [
                    field.citation(ctx.report.doc, "Header, protocol reference"),
                    ver_field.citation(ctx.protocol.doc, "Header, version") if ver_field else None,
                    reporting,
                ],
            )
        ],
        "findings",
        "",
    )


@rule("R-02", "Report cites the correct protocol document", "identity",
      "Does the protocol document number named by the report match the protocol supplied?")
def r02(ctx: Ctx):
    me = _me(r02)
    ref_id, _, field = ex.protocol_reference(ctx.report)
    actual = ex.doc_id(ctx.protocol)
    if field is None or ref_id is None or actual is None:
        return [], "not-applicable", "Report does not name a protocol document number."
    if ref_id == actual:
        return [], "no-finding", f"Both documents use {actual}."
    doc_field = ctx.protocol.field("Document")
    return (
        [
            _f(me, "document", "high",
               f"The report states that it verifies protocol {ref_id}. The protocol supplied is {actual}.",
               "A verification report must be traceable to the protocol it satisfies.",
               "Confirm which protocol this report belongs to before reviewing any result.",
               [field.citation(ctx.report.doc, "Header, protocol reference"),
                doc_field.citation(ctx.protocol.doc, "Header, document number") if doc_field else None])
        ],
        "findings",
        "",
    )


@rule("R-03", "Report is the one the protocol names", "identity",
      "Does the report's document number match the report the protocol says results go into?")
def r03(ctx: Ctx):
    me = _me(r03)
    reporting = ctx.protocol.section("Reporting")
    report_id = ex.doc_id(ctx.report)
    if reporting is None or report_id is None:
        return [], "not-applicable", "Protocol does not name a target report."
    text = " ".join(
        ctx.protocol.doc.raw_line(reporting.page, ln)
        for ln in range(reporting.start, reporting.end)
    )
    named = ex.DOC_ID.findall(text)
    if not named:
        return [], "not-applicable", "Protocol reporting section names no report number."
    if report_id in named:
        return [], "no-finding", f"Protocol names {report_id}; report is {report_id}."
    doc_field = ctx.report.field("Document")
    return (
        [
            _f(me, "document", "high",
               f"The protocol directs results into {named[0]}. This report is numbered {report_id}.",
               "Results must be recorded in the report the protocol names.",
               "Confirm this is the report intended to satisfy the protocol.",
               [reporting.citation(ctx.protocol.doc),
                doc_field.citation(ctx.report.doc, "Header, document number") if doc_field else None])
        ],
        "findings",
        "",
    )


# =====================================================================
# Equipment, calibration and dates
# =====================================================================

@rule("R-04", "Instrument calibration current at time of testing", "equipment",
      "Is the calibration due date of the reported equipment later than the reported test date?")
def r04(ctx: Ctx):
    me = _me(r04)
    equip_text, cal_due, equip_field = ex.equipment(ctx.report)
    rep_date, date_field = ex.report_date(ctx.report)
    requirement = ctx.protocol.cite_phrase(r"within current calibration", "Section 2, General requirements")
    if cal_due is None or equip_field is None:
        return [], "not-applicable", "Report states no calibration due date."
    if rep_date is None:
        return [], "not-applicable", "Report states no date to compare calibration against."
    if cal_due >= rep_date:
        return [], "no-finding", f"Calibration due {cal_due:%d %b %Y} is not before the report date."
    days = (rep_date - cal_due).days
    return (
        [
            _f(me, "document", "high",
               f"The report records the test equipment's calibration as due {cal_due:%d %B %Y}, "
               f"which is {days} days before the report date of {rep_date:%d %B %Y}.",
               "The protocol requires all measuring instruments to be within current calibration "
               "at the time of testing.",
               "Obtain the calibration certificate covering the actual test dates, or record this "
               "as a deviation with an impact assessment.",
               [requirement,
                equip_field.citation(ctx.report.doc, "Header, test equipment"),
                date_field.citation(ctx.report.doc, "Header, date") if date_field else None],
               uncertainty="The report does not state when testing took place, so the report date "
                           "has been used as a proxy. If testing predates the report, the gap may differ."),
        ],
        "findings",
        "",
    )


@rule("R-05", "Testing falls after the protocol became effective", "dates",
      "Is the reported date on or after the protocol's effective date?")
def r05(ctx: Ctx):
    me = _me(r05)
    eff, eff_field = ex.effective_date(ctx.protocol)
    rep_date, date_field = ex.report_date(ctx.report)
    if eff is None or rep_date is None:
        return [], "not-applicable", "One or both dates are absent."
    if rep_date >= eff:
        return [], "no-finding", f"Report dated {rep_date:%d %b %Y}, protocol effective {eff:%d %b %Y}."
    return (
        [
            _f(me, "document", "high",
               f"The report is dated {rep_date:%d %B %Y}, before the protocol's effective date of "
               f"{eff:%d %B %Y}.",
               "Testing is expected to be carried out under an effective protocol version.",
               "Establish which protocol version was in force when testing was performed.",
               [eff_field.citation(ctx.protocol.doc, "Header, effective date") if eff_field else None,
                date_field.citation(ctx.report.doc, "Header, date") if date_field else None])
        ],
        "findings",
        "",
    )


@rule("R-06", "Date of testing is stated", "dates",
      "Does the report state when testing was actually carried out?")
def r06(ctx: Ctx):
    me = _me(r06)
    if ctx.report.doc.contains(r"test(?:ing|ed)?\s+(?:date|dates|performed|carried out)\s*[:\-]"):
        return [], "no-finding", "Report states a testing date."
    _, date_field = ex.report_date(ctx.report)
    requirement = ctx.protocol.cite_phrase(r"within current calibration", "Section 2, General requirements")
    return (
        [
            _f(me, "document", "low",
               "The report gives a document date but does not state the date or dates on which "
               "testing was carried out.",
               "The protocol ties calibration currency to the time of testing, which cannot be "
               "confirmed without test dates.",
               "Ask for the test dates, or the raw data references that carry them.",
               [requirement,
                date_field.citation(ctx.report.doc, "Header, date") if date_field else None])
        ],
        "findings",
        "",
    )


@rule("R-19", "Equipment named by the protocol was used", "equipment",
      "Is each instrument named in the protocol's method column also named in the report?")
def r19(ctx: Ctx):
    me = _me(r19)
    findings, checked = [], []
    for tid in ctx.protocol.test_ids():
        row = ctx.protocol.rows()[tid]
        method = row.text("method")
        for token in re.findall(r"\b([A-Z][A-Za-z]{2,}\s+\d{3,5})\b", method):
            if token.split()[0].upper() in STANDARDS:
                continue
            checked.append(f"{tid}:{token}")
            if not ctx.report.doc.contains(re.escape(token)):
                findings.append(
                    _f(me, tid, "medium",
                       f"The protocol specifies {token} for {tid}. The report does not name it.",
                       "The protocol specifies the instrument for this test.",
                       "Confirm which instrument was used and that it was qualified for the test.",
                       [row.cell("method").citation(ctx.protocol.doc.key, f"{tid} method / conditions")])
                )
    if not checked:
        return [], "not-applicable", "Protocol names no specific instruments."
    if findings:
        return findings, "findings", ""
    return [], "no-finding", "Named instrument(s) present in report: " + ", ".join(checked)


# =====================================================================
# Test coverage
# =====================================================================

@rule("R-10", "Every protocol test is reported", "coverage",
      "Does the report contain a result row for each test in the protocol?")
def r10(ctx: Ctx):
    me = _me(r10)
    reported = ctx.report.rows()
    missing = [t for t in ctx.protocol.test_ids() if t not in reported]
    if not missing:
        return [], "no-finding", f"All {len(ctx.protocol.test_ids())} protocol tests appear in the report."
    reporting = ctx.protocol.cite_phrase(r"shall be recorded", "Section 4, Reporting")
    findings = []
    for tid in missing:
        row = ctx.protocol.rows()[tid]
        findings.append(
            _f(me, tid, "high",
               f"{tid} ({row.text('test_name')}) is required by the protocol but has no result row "
               f"in the report. The report's results table contains "
               f"{', '.join(ctx.report.test_ids())}.",
               "The protocol requires results for all five tests (T1 to T5) to be recorded in this report.",
               "Establish whether this test was performed and recorded elsewhere, or not performed. "
               "Verification coverage is incomplete until this is resolved.",
               [row.cell("test_id").citation(ctx.protocol.doc.key, f"{tid} row"),
                row.cell("test_name").citation(ctx.protocol.doc.key, f"{tid} test"),
                row.cell("criterion").citation(ctx.protocol.doc.key, f"{tid} acceptance criterion"),
                reporting,
                # Evidence of the absence: every test ID the report's table
                # actually carries, quoted from the table itself.
                Citation(ctx.report.doc.key,
                         [s for r in ctx.report.table.rows for s in r.cell("test_id").spans],
                         "Test IDs present in the report's results table")])
        )
    return findings, "findings", ""


@rule("R-11", "No unplanned tests reported", "coverage",
      "Does the report contain result rows for tests the protocol does not define?")
def r11(ctx: Ctx):
    me = _me(r11)
    planned = set(ctx.protocol.test_ids())
    extra = [t for t in ctx.report.test_ids() if t not in planned]
    if not extra:
        return [], "no-finding", "Report contains no tests outside the protocol."
    findings = []
    for tid in extra:
        row = ctx.report.rows()[tid]
        findings.append(
            _f(me, tid, "medium",
               f"The report records {tid} ({row.text('test_name')}), which is not defined in this protocol.",
               "The protocol defines the set of tests this report is assessed against.",
               "Confirm the source of this test's acceptance criterion.",
               [row.cell("test_id").citation(ctx.report.doc.key, f"{tid} row")])
        )
    return findings, "findings", ""


@rule("R-18", "Protocol states a usable sample size", "protocol-quality",
      "Does every protocol test give a numeric sample size?")
def r18(ctx: Ctx):
    me = _me(r18)
    findings = []
    for tid in ctx.protocol.test_ids():
        row = ctx.protocol.rows()[tid]
        text = row.text("sample_size")
        if text and parse_int(text) is None:
            findings.append(
                _f(me, tid, "low",
                   f"The protocol's sample size for {tid} reads \"{text}\" rather than a number, so "
                   f"the number of units required for this test cannot be determined from the protocol.",
                   "The protocol's sample size column is the basis for checking how many units were tested.",
                   "Confirm the required sample size for this test from the referenced standard or plan; "
                   "this tool cannot check sample size for it.",
                   [row.cell("sample_size").citation(ctx.protocol.doc.key, f"{tid} sample size"),
                    row.cell("method").citation(ctx.protocol.doc.key, f"{tid} method / conditions")])
            )
    if findings:
        return findings, "findings", ""
    return [], "no-finding", "All protocol tests give a numeric sample size."


# =====================================================================
# Criteria, sampling, conditions, results
# =====================================================================

@rule("R-12", "Report restates the protocol's acceptance criterion", "criteria",
      "For each test, does the criterion printed in the report match the protocol's?")
def r12(ctx: Ctx):
    me = _me(r12)
    findings = []
    for tid in ctx.shared_tests():
        p_row, r_row = ctx.protocol.rows()[tid], ctx.report.rows()[tid]
        p_text, r_text = p_row.text("criterion"), r_row.text("criterion")
        if not p_text or not r_text or normalise(p_text) == normalise(r_text):
            continue
        p_crit, r_crit = parse_criterion(p_text), parse_criterion(r_text)
        direction = _stringency(p_crit, r_crit)
        findings.append(
            _f(me, tid, "high",
               f"The acceptance criterion printed in the report for {tid} is \"{r_text}\". "
               f"The protocol requires \"{p_text}\".{direction}",
               "The report is assessed against the protocol's acceptance criteria.",
               "Treat the protocol criterion as the one that applies. Establish why the report "
               "carries a different figure and whether results were dispositioned against it.",
               [p_row.cell("criterion").citation(ctx.protocol.doc.key, f"{tid} acceptance criterion"),
                r_row.cell("criterion").citation(ctx.report.doc.key, f"{tid} acceptance criterion")])
        )
    if findings:
        return findings, "findings", ""
    return [], "no-finding", f"Criteria match for {', '.join(ctx.shared_tests())}."


def _stringency(p_crit, r_crit) -> str:
    if isinstance(p_crit, Threshold) and isinstance(r_crit, Threshold) and p_crit.op == r_crit.op:
        if p_crit.outside(r_crit.value):
            return " The figure in the report is less demanding than the protocol's."
        return " The figure in the report is more demanding than the protocol's."
    return ""


@rule("R-13", "Sample size meets the protocol", "sampling",
      "For each test, is the number of units tested at least the protocol's sample size?")
def r13(ctx: Ctx):
    me = _me(r13)
    findings, compared = [], []
    for tid in ctx.shared_tests():
        p_row, r_row = ctx.protocol.rows()[tid], ctx.report.rows()[tid]
        required = parse_int(p_row.text("sample_size"))
        tested = parse_int(r_row.text("sample_size"))
        if required is None or tested is None:
            continue
        compared.append(tid)
        if tested == required:
            continue
        low = tested < required
        findings.append(
            _f(me, tid, "high" if low else "low",
               f"The report records {tested} units tested for {tid}. The protocol requires {required}."
               + (f" That is {required - tested} fewer than required." if low
                  else " That is more than required."),
               "The protocol fixes the sample size for each test.",
               "A shortfall in sample size affects the statistical basis of the result. Establish "
               "whether a justified deviation exists." if low else
               "Confirm the additional units are accounted for in the raw data.",
               [p_row.cell("sample_size").citation(ctx.protocol.doc.key, f"{tid} sample size"),
                r_row.cell("sample_size").citation(ctx.report.doc.key, f"{tid} n tested")])
        )
    if findings:
        return findings, "findings", ""
    return [], "no-finding", f"Sample sizes match for {', '.join(compared)}."


@rule("R-16", "Test conditions match the protocol method", "conditions",
      "Do the conditions described in the report contradict the protocol's method column?")
def r16(ctx: Ctx):
    me = _me(r16)
    findings, checked = [], []
    for tid in ctx.shared_tests():
        p_row, r_row = ctx.protocol.rows()[tid], ctx.report.rows()[tid]
        method = p_row.text("method")
        reported = " ".join(filter(None, [r_row.text("result"), r_row.text("method")]))
        spec_temps = temperatures(method)
        if not spec_temps:
            continue
        checked.append(tid)
        rep_temps = temperatures(reported)
        conflict = None
        if any(abs(t - spec_temps[0]) > 0.01 for t in rep_temps):
            conflict = f"a different temperature ({', '.join(f'{t:g} C' for t in rep_temps)})"
        elif re.search(r"\b(ambient|room temperature)\b", reported, re.I) and not rep_temps:
            conflict = "ambient / room temperature"
        if not conflict:
            continue
        findings.append(
            _f(me, tid, "high",
               f"The report records {tid} as tested at {conflict}. The protocol specifies "
               f"\"{method}\".",
               "The protocol fixes the test conditions; results obtained under other conditions "
               "do not demonstrate the same thing.",
               "Establish whether testing at these conditions was authorised, and what the effect on "
               "the measured property is. This is a change of test method, not only of paperwork.",
               [p_row.cell("method").citation(ctx.protocol.doc.key, f"{tid} method / conditions"),
                r_row.cell("result").citation(ctx.report.doc.key, f"{tid} result and disposition")])
        )
    if not checked:
        return [], "not-applicable", "Protocol method column specifies no comparable conditions."
    if findings:
        return findings, "findings", ""
    return [], "no-finding", f"No contradicting conditions found for {', '.join(checked)}."


@rule("R-14", "Reported values sit inside the protocol criterion", "results",
      "For each test, do the values in the report lie within the PROTOCOL's acceptance criterion?")
def r14(ctx: Ctx):
    me = _me(r14)
    findings, compared = [], []
    for tid in ctx.shared_tests():
        p_row, r_row = ctx.protocol.rows()[tid], ctx.report.rows()[tid]
        crit_text, result_text = p_row.text("criterion"), r_row.text("result")
        crit = parse_criterion(crit_text)
        if crit is None or isinstance(crit, Qualitative):
            continue
        values = parse_measurements(result_text, getattr(crit, "prefix", ""))
        if not values:
            continue
        compared.append(tid)
        outside = [v for v in worst_case(crit, values) if crit.outside(v.value)]
        if not outside:
            continue

        worst = min(outside, key=lambda v: v.value) if isinstance(crit, Threshold) and crit.op == ">=" \
            else max(outside, key=lambda v: v.value)
        means = [v for v in values if v.label == "mean"]
        uncertainty = ""
        if isinstance(crit, Threshold) and means and not crit.outside(means[0].value):
            uncertainty = (
                f"The protocol does not state whether \"{crit_text}\" applies to each unit or to the "
                f"sample mean. The reported mean ({means[0].value:g} {means[0].unit}) is on the "
                f"compliant side of the criterion while the reported {worst.label} is not, so the "
                f"answer depends on which reading applies. A reviewer needs to settle this."
            )
        findings.append(
            _f(me, tid, "high",
               f"For {tid} the report records \"{squash(worst.source)}\". The protocol's acceptance "
               f"criterion is \"{crit_text}\". The reported value lies outside it.",
               "Reported values are assessed against the protocol's acceptance criterion.",
               "Check the raw data for this test and decide the disposition. This tool does not "
               "determine whether the test passed or failed.",
               [p_row.cell("criterion").citation(ctx.protocol.doc.key, f"{tid} acceptance criterion"),
                r_row.cell("result").citation(ctx.report.doc.key, f"{tid} result and disposition")],
               uncertainty=uncertainty)
        )
    if findings:
        return findings, "findings", ""
    if not compared:
        return [], "not-applicable", "No numeric results available to compare."
    return [], "no-finding", f"Reported values sit inside the protocol criterion for {', '.join(compared)}."


@rule("R-22", "Qualitative criteria are evidenced in full", "results",
      "Where a criterion carries a quantified qualifier (e.g. 'at 24 h'), does the result restate it?")
def r22(ctx: Ctx):
    me = _me(r22)
    findings, checked = [], []
    for tid in ctx.shared_tests():
        p_row, r_row = ctx.protocol.rows()[tid], ctx.report.rows()[tid]
        crit_text, result_text = p_row.text("criterion"), r_row.text("result")
        if not isinstance(parse_criterion(crit_text), Qualitative):
            continue
        quals = quantified_qualifiers(crit_text)
        if not quals:
            continue
        checked.append(tid)
        missing = [q for q in quals if normalise(q) not in normalise(result_text)]
        if not missing:
            continue
        findings.append(
            _f(me, tid, "low",
               f"The protocol's criterion for {tid} is \"{crit_text}\". The report records "
               f"\"{result_text}\" without restating the {', '.join(missing)} condition.",
               "A qualitative criterion is only evidenced when the qualifying condition is evidenced too.",
               "Confirm from the raw data that the observation was made at the required point, and "
               "that the report wording is simply abbreviated.",
               [p_row.cell("criterion").citation(ctx.protocol.doc.key, f"{tid} acceptance criterion"),
                r_row.cell("result").citation(ctx.report.doc.key, f"{tid} result and disposition")])
        )
    if not checked:
        return [], "not-applicable", "No qualitative criteria with quantified qualifiers."
    if findings:
        return findings, "findings", ""
    return [], "no-finding", f"Qualifiers restated for {', '.join(checked)}."


@rule("R-15", "Recorded disposition is consistent with the recorded values", "claims",
      "Does the report record a passing disposition for a test whose values fall outside the protocol criterion?")
def r15(ctx: Ctx):
    me = _me(r15)
    findings = []
    for f in ctx.fired("R-14"):
        tid = f.scope
        r_row = ctx.report.rows()[tid]
        result_text = r_row.text("result")
        if not re.search(r"\b(pass|passed|conform(?:s|ing)?|meets)\b", result_text, re.I):
            continue
        p_row = ctx.protocol.rows()[tid]
        findings.append(
            _f(me, tid, "medium",
               f"The report records the disposition for {tid} as \"{squash(result_text)}\", while the "
               f"values in that same entry fall outside the protocol criterion "
               f"\"{p_row.text('criterion')}\".",
               "A recorded disposition should follow from the recorded data.",
               "Resolve the inconsistency between the recorded values and the recorded disposition. "
               "The disposition is the reviewer's to determine, not this tool's.",
               [p_row.cell("criterion").citation(ctx.protocol.doc.key, f"{tid} acceptance criterion"),
                r_row.cell("result").citation(ctx.report.doc.key, f"{tid} result and disposition")])
        )
    if findings:
        return findings, "findings", ""
    return [], "no-finding", "No passing disposition contradicts its own recorded values."


@rule("R-17", "Deviations are documented", "deviations",
      "Where this tool detected a departure from the protocol, does the report document a deviation?")
def r17(ctx: Ctx):
    me = _me(r17)
    departures = ctx.fired("R-13") + ctx.fired("R-16") + ctx.fired("R-12")
    if not departures:
        return [], "not-applicable", "No departures from the protocol were detected to look for."
    if ctx.report.doc.contains(r"deviation"):
        return [], "no-finding", "Report mentions deviations."
    requirement = ctx.protocol.cite_phrase(r"[Aa]ny deviation", "Section 2, General requirements")
    headings = [s for s in ctx.report.sections]
    heading_cite = ctx.report.doc.line_citation(
        headings[0].page, [s.start for s in headings], "Report section headings")
    scopes = sorted({f.scope for f in departures})
    return (
        [
            _f(me, "document", "high",
               "The report contains no deviation record. The word \"deviation\" does not appear "
               f"anywhere in it, and its sections are limited to "
               f"{', '.join(s.title for s in headings)}. Departures from the protocol were "
               f"nevertheless identified for {', '.join(scopes)}.",
               "The protocol requires any deviation from it to be documented and justified in the "
               "verification report.",
               "Each departure listed in this review needs either a documented, justified deviation "
               "or a correction to the report.",
               [requirement, heading_cite])
        ],
        "findings",
        "",
    )


# =====================================================================
# Overall claims made by the report
# =====================================================================

@rule("R-20", "Summary claim is supported by the report's own table", "claims",
      "Does a blanket conformance statement in the summary sit alongside contradicting entries?")
def r20(ctx: Ctx):
    me = _me(r20)
    contradicting = ctx.fired("R-14")
    missing = ctx.fired("R-10")
    if not contradicting and not missing:
        return [], "no-finding", "No blanket claim to challenge."
    claim = ctx.report.cite_phrase(r"all tests", "Section 1, Summary")
    if claim is None:
        return [], "no-finding", "Report makes no blanket conformance statement."
    parts = []
    if contradicting:
        parts.append(
            f"values outside the protocol criterion are recorded for "
            f"{', '.join(sorted({f.scope for f in contradicting}))}")
    if missing:
        parts.append(f"no result is recorded for {', '.join(sorted({f.scope for f in missing}))}")
    return (
        [
            _f(me, "document", "medium",
               "The summary states a blanket conformance position for the whole report, but "
               + " and ".join(parts) + ".",
               "A summary statement should be supported by the entries beneath it.",
               "The summary needs to be reconciled with the table, whichever way the individual "
               "dispositions are eventually decided.",
               [claim] + [c for f in contradicting[:1] for c in f.citations[-1:]])
        ],
        "findings",
        "",
    )


@rule("R-21", "Conclusion is supported by the verification performed", "claims",
      "Does the conclusion claim overall conformance while required tests are missing or contested?")
def r21(ctx: Ctx):
    me = _me(r21)
    missing = ctx.fired("R-10")
    contested = ctx.fired("R-14")
    if not missing and not contested:
        return [], "no-finding", "Nothing outstanding that the conclusion would overstate."
    section = ctx.report.section("Conclusion")
    if section is None:
        return [], "not-applicable", "Report has no conclusion section."
    reporting = ctx.protocol.cite_phrase(r"shall be recorded", "Section 4, Reporting")
    reasons = []
    if missing:
        reasons.append(f"{', '.join(sorted({f.scope for f in missing}))} is not reported at all")
    if contested:
        reasons.append(
            f"{', '.join(sorted({f.scope for f in contested}))} carries values outside the protocol criterion")
    return (
        [
            _f(me, "document", "medium",
               "The conclusion states that the device meets its verification requirements and "
               "recommends release, while " + " and ".join(reasons) + ".",
               "The protocol requires results for all five tests before verification is complete.",
               "Verification coverage and the outstanding results need to be settled before the "
               "conclusion can stand. Release is a decision for the reviewer and the design team.",
               [section.citation(ctx.report.doc), reporting])
        ],
        "findings",
        "",
    )


# =====================================================================

PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def run_rules(protocol: ex.ParsedDoc, report: ex.ParsedDoc) -> Tuple[List[Finding], List[RuleOutcome]]:
    ctx = Ctx(protocol=protocol, report=report, findings=[])
    outcomes: List[RuleOutcome] = []
    for r in REGISTRY:
        findings, status, detail = r.fn(ctx)
        ctx.findings.extend(findings)
        outcomes.append(RuleOutcome(r.id, r.title, r.category, r.question,
                                    len(findings), status, detail))

    ordered = sorted(
        ctx.findings,
        key=lambda f: (PRIORITY_ORDER.get(f.priority, 3), f.rule_id, f.scope),
    )
    for i, f in enumerate(ordered, start=1):
        f.id = f"F-{i:03d}"
    return ordered, outcomes
