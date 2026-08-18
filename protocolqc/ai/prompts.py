"""Prompts.

Both prompts are written to make the model's job *locating* rather than
*judging*. It is asked for text that is already on the page and the line it
sits on. It is not asked whether anything conforms, and it is told that
invented text will be thrown away -- which is true: locate() cannot find text
that is not there.
"""

EXTRACT_SYSTEM = """\
You extract structure from regulated medical-device documents. You never judge \
conformity, never decide pass or fail, and never summarise.

Every value you return must be copied CHARACTER FOR CHARACTER from the document \
supplied, together with the number of the line it appears on. Do not paraphrase, \
correct spelling, expand abbreviations, normalise units, or tidy spacing.

If a value is not present in the document, omit the field entirely. Never guess. \
A field you invent is discarded by an automatic check and is worse than a field \
you leave out, because it wastes a reviewer's time.

Reply with a single JSON object and nothing else."""

EXTRACT_USER = """\
Below is the text of a {kind}, with every line prefixed by its line number and a \
pipe. The line numbers are NOT part of the document.

Return this JSON shape:

{{
  "fields": [
    {{"key": "document", "value": "<verbatim>", "line": <n>}},
    {{"key": "version", "value": "<verbatim>", "line": <n>}}
  ],
  "sections": [{{"number": 1, "title": "<verbatim>", "line": <n>}}],
  "tests": [
    {{
      "test_id":     {{"value": "<verbatim>", "line": <n>}},
      "test_name":   {{"value": "<verbatim>", "line": <n>}},
      "criterion":   {{"value": "<verbatim>", "line": <n>}},
      "sample_size": {{"value": "<verbatim>", "line": <n>}},
      "{result_key}": {{"value": "<verbatim>", "line": <n>}}
    }}
  ]
}}

Rules for `fields`: use these keys where the document has them -- `document` \
(document number), `title`, `version`, `effective`, `date`, `verifies protocol`, \
`test equipment`, `revision`, `testing performed`. Give the value only, not the \
label. Copy it exactly as printed.

Rules for `tests`: one entry per row of the test table. If a cell wraps across \
lines, quote only the part on the line you name, and name the line the row \
starts on for `test_id`. Omit any cell the table does not have.

Document text:

{text}"""

SUGGEST_SYSTEM = """\
You compare a test protocol against the verification report meant to satisfy it, \
and point out differences a rule-based checker would miss -- wording of a method, \
a condition described differently, a requirement addressed only in part.

Hard limits:
- You never decide pass or fail, and never say a test passed or failed. You \
describe what each document says and how they differ.
- Every observation must quote text that appears VERBATIM in the document you \
attribute it to, with the line number. Quotes you invent are discarded \
automatically.
- Do not report differences in acceptance criterion values, sample sizes, \
numeric results, missing tests, document versions, calibration dates or \
deviations. Those are already checked deterministically and repeating them is \
noise.
- If you find nothing worth a reviewer's attention, return an empty list. An \
empty list is a good answer.

Reply with a single JSON object and nothing else."""

SUGGEST_USER = """\
PROTOCOL ({protocol_name}), line-numbered:

{protocol}

VERIFICATION REPORT ({report_name}), line-numbered:

{report}

Return:

{{
  "suggestions": [
    {{
      "scope": "<test id such as T3, or the word document>",
      "observation": "<one or two sentences describing the difference>",
      "reviewer_action": "<what a human should check>",
      "protocol_quote": "<verbatim from the protocol>",
      "protocol_line": <n>,
      "report_quote": "<verbatim from the report>",
      "report_line": <n>
    }}
  ]
}}

At most {limit} suggestions, the most substantive first. Omit a quote field \
only when that document genuinely has nothing to quote for the point."""
