"""Command line entry point.

Note on exit codes: the process exits 0 when the review completes, whether or
not findings were raised, and non-zero only when the *tool* failed (a document
could not be parsed, or a citation could not be verified). Findings must not
influence the exit code -- an exit code that encoded "clean" would be a
pass/fail verdict by the back door, and this tool does not issue one.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .ai.client import AIUnavailable, client_from_env
from .pipeline import review
from .render import to_html, to_json
from .table import TableParseError
from .verify import CitationError


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="protocolqc",
        description="Compare a verification report against its test protocol and flag "
                    "differences, with a citation to the exact text behind each one. "
                    "Decision support for a human reviewer; it does not decide pass or fail.",
    )
    ap.add_argument("--protocol", required=True, help="test protocol PDF")
    ap.add_argument("--report", required=True, help="verification report PDF")
    ap.add_argument("--out", default="out", help="output directory (default: out)")
    ap.add_argument("--quiet", action="store_true", help="suppress the console summary")
    ap.add_argument("--ai", action="store_true",
                    help="allow a model to locate structure in documents the parser "
                         "does not recognise (needs NVIDIA_API_KEY)")
    ap.add_argument("--ai-suggest", action="store_true",
                    help="additionally ask the model for advisory differences the rules "
                         "do not model; implies --ai")
    ap.add_argument("--ai-model", default=None,
                    help="NVIDIA NIM model id (default: meta/llama-3.3-70b-instruct)")
    args = ap.parse_args(argv)

    ai_client = None
    if args.ai or args.ai_suggest:
        try:
            ai_client = client_from_env(args.ai_model)
            print(f"AI assistance: {ai_client.describe()}", file=sys.stderr)
            print(f"  key {ai_client.describe_key()}", file=sys.stderr)
        except AIUnavailable as exc:
            print(f"warning: {exc}", file=sys.stderr)
            print("Continuing without AI. The deterministic checks are unaffected.",
                  file=sys.stderr)

    try:
        result = review(args.protocol, args.report, ai_client=ai_client,
                        want_suggestions=args.ai_suggest)
    except TableParseError as exc:
        print(f"error: {exc}", file=sys.stderr)
        print("The tool stops rather than guess at a table it does not recognise.", file=sys.stderr)
        if ai_client is None:
            print("If this is a document from a different template, try --ai.", file=sys.stderr)
        return 2
    except CitationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "findings.json"
    html_path = out_dir / "review-sheet.html"
    json_path.write_text(
        to_json(result.findings, result.outcomes, result.limits, result.manifest_data,
                result.repairer, result.suggestions), encoding="utf-8")
    html_path.write_text(
        to_html(result.findings, result.outcomes, result.limits, result.manifest_data,
                result.doc_names, result.repairer, result.suggestions), encoding="utf-8")

    if not args.quiet:
        _summarise(result.findings, result.outcomes, result.verification,
                   json_path, html_path, result.repairer)
        for note in result.ai_notes:
            print(f"  ai: {note}")
        if result.suggestions:
            print(f"  ai: {len(result.suggestions)} advisory suggestion(s), "
                  f"listed separately from the {len(result.findings)} rule finding(s)")
    return 0


def _summarise(findings, outcomes, verification, json_path, html_path, repairer) -> None:
    width = 78
    print("=" * width)
    print("protocol-to-report review  |  decision support only, not a pass/fail verdict")
    print("=" * width)
    for f in findings:
        head = f"{f.id}  [{f.priority:<6}] {f.scope:<8} {f.rule_id}  {f.rule_title}"
        print(f"\n{head}")
        print(f"    {f.statement}")
        for c in f.citations:
            quote = repairer.quote(c).replace("\n", " / ")
            print(f"      - {c.doc:<8} {c.locator:<14} “{_clip(quote)}”")
        if f.uncertainty:
            print(f"    ? {f.uncertainty}")

    silent = [o for o in outcomes if o.status == "no-finding"]
    na = [o for o in outcomes if o.status == "not-applicable"]
    print("\n" + "-" * width)
    print(f"{len(findings)} finding(s) for review: "
          f"{sum(1 for f in findings if f.priority == 'high')} high, "
          f"{sum(1 for f in findings if f.priority == 'medium')} medium, "
          f"{sum(1 for f in findings if f.priority == 'low')} low")
    print(f"{len(silent)} check(s) ran and found nothing; {len(na)} not applicable")
    print(f"{verification.citations_checked} citations / {verification.spans_checked} text spans "
          f"re-read from source and matched")
    print(f"\n  {html_path}   <- open this for review")
    print(f"  {json_path}   <- audit record")
    print("-" * width)


def _clip(text: str, width: int = 84) -> str:
    return text if len(text) <= width else text[: width - 1] + "…"


if __name__ == "__main__":
    raise SystemExit(main())
