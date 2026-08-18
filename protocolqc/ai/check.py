"""Preflight for the AI path: does a real key reach a real model, and does the
safety gate still hold when it does?

Every other AI test runs offline against a stub, deliberately -- a suite that
needs a key and a network is a suite nobody runs. The one property that cannot
be checked that way is whether the thing works at all against the live API.
This is that check, kept out of the test suite so it never turns a clean
checkout red, and meant to be run before a demonstration rather than during
one.

    python -m protocolqc.ai.check

Exit codes: 0 ready, 1 no key configured, 2 the API call failed, 3 the call
worked but the round trip produced nothing usable.
"""

from __future__ import annotations

import json
import sys
import time
from typing import Optional

from ..model import Document
from .client import NO_KEY_MESSAGE, AIUnavailable, client_from_env, list_models
from .locate import LocateStats, locate, numbered

# A miniature document with one unambiguous fact to quote back. Short on
# purpose: this is a connectivity check, not a benchmark.
SAMPLE = """SECTION 4  ACCEPTANCE CRITERIA
T1  Tensile strength       >= 5.0 N after 24 h immersion
T2  Dimensional tolerance  12.00 +/- 0.15 mm
T3  Seal peel force        0.20 - 0.40 N
"""

SYSTEM = (
    "You locate text in documents. You never judge, score or summarise. "
    "Reply with JSON only."
)

TASK = (
    "Below is a document with numbered lines. Return the line that states the "
    "tensile strength criterion, as JSON: "
    '{"line": <line number>, "quote": "<the text exactly as it appears>"}. '
    "Copy the text character for character. Do not add or reword anything.\n\n"
)


def _ok(msg: str) -> None:
    print(f"  ok    {msg}")


def _bad(msg: str) -> None:
    print(f"  FAIL  {msg}")


def main(argv: Optional[list] = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(
        prog="protocolqc.ai.check",
        description="Check that the optional AI path is configured and reachable.",
    )
    ap.add_argument("--model", default=None, help="model id to test (default: the configured one)")
    ap.add_argument("--list-models", action="store_true",
                    help="print the model ids the endpoint advertises, and stop")
    args = ap.parse_args(argv)

    if args.list_models:
        try:
            for mid in list_models():
                print(mid)
        except AIUnavailable as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        return 0

    print("AI preflight — the deterministic checks do not depend on any of this")
    print("-" * 72)

    # 1. Is a key configured, and where did it come from?
    try:
        client = client_from_env(args.model)
    except AIUnavailable:
        _bad("no key configured")
        print("\n" + NO_KEY_MESSAGE)
        print("\nThe tool still runs without one:")
        print("    python run.py --protocol a.pdf --report b.pdf")
        return 1
    _ok(f"key {client.describe_key()}")
    _ok(f"endpoint {client.base_url}")
    _ok(f"model {client.model}")

    # 2. Does the endpoint accept it?
    started = time.time()
    try:
        raw = client.complete(SYSTEM, TASK + numbered(_doc()))
    except AIUnavailable as exc:
        _bad(f"the API call did not succeed: {exc}")
        print("\nIf the key was rejected, check it was pasted whole. If the model was")
        print("not found, list what this endpoint offers:")
        print("    python -m protocolqc.ai.check --list-models")
        return 2
    elapsed = time.time() - started
    _ok(f"live call returned in {elapsed:.1f}s "
        f"({client.usage.prompt_tokens} prompt / {client.usage.completion_tokens} completion tokens)")

    # 3. Did it come back as usable JSON?
    try:
        payload = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
    except Exception:
        _bad(f"the reply was not JSON: {raw[:120]!r}")
        print("\nThis model may not honour response_format. Try another:")
        print("    python -m protocolqc.ai.check --model nvidia/llama-3.1-nemotron-70b-instruct")
        return 3

    # 4. The part that actually matters: does its quote survive the gate?
    doc = _doc()
    stats = LocateStats()
    span = locate(doc, str(payload.get("quote") or ""), payload.get("line"),
                  stats=stats, what="preflight")
    if span is None:
        _bad("the model's quote is not in the document, so it was discarded")
        print(f"        it returned: {str(payload.get('quote'))[:90]!r}")
        print("        That is the gate working, but it means this model is a poor")
        print("        fit for locating text. Try a different one.")
        return 3
    _ok(f"quote located at p.{span.page} line {span.line}: {span.text.strip()!r}")
    if stats.line_hint_wrong:
        _ok("the model's line number was wrong and the search corrected it "
            "— the citation points at the real location")

    # 5. Negative control, offline: a fabricated quote must not survive.
    fake = LocateStats()
    if locate(doc, "Tensile strength >= 9.9 N after 24 h", 2, stats=fake) is not None:
        _bad("a quote that is NOT in the document was located — the gate is broken")
        return 3
    _ok("a fabricated quote was refused (negative control)")

    print("-" * 72)
    print("Ready. Turn it on with --ai, and --ai-suggest for advisory observations.")
    print("The model locates text; it never decides anything.")
    return 0


def _doc() -> Document:
    return Document.from_text("report", "preflight-sample", SAMPLE)


if __name__ == "__main__":
    raise SystemExit(main())
