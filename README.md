# protocolqc — protocol-to-report discrepancy review

A prototype that reads a test protocol and its verification report, and flags where
the report does not do what the protocol required. Every flag carries the exact text
from both documents, with page and line, so a reviewer can check it against the PDF.

**It does not decide pass or fail.** It surfaces differences, with evidence, for a
qualified human to judge. It is not qualified software and its output is not a
validated record.

## Run it

```bash
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt

./.venv/bin/python run.py \
    --protocol sample-a-test-protocol-nv-200.pdf \
    --report   sample-b-verification-report-nv-200.pdf
```

Or run the whole demonstration — the sample pair and the corrected pair, one after
the other — with `./demo.sh`.

Writes two files to `out/`:

| file | for |
| --- | --- |
| `review-sheet.html` | the reviewer — open in a browser, work down the findings, record a decision against each |
| `findings.json` | the audit trail — findings, citations with character offsets, every rule that ran, input file SHA-256s |

Tests:

```bash
PYTHONPATH=. ./.venv/bin/python -m unittest discover -s tests -t tests
```

Rebuilding the review sheet's interface (only needed if you change `ui/`):

```bash
cd ui && npm install && node build.mjs
```

## Upload your own documents

For anyone who is not going to use a command line, there is a local web app:

```bash
./.venv/bin/python -m protocolqc.server          # http://127.0.0.1:8000
```

Drop in a protocol and a report, press review, and you get the same review sheet.
Completed runs are written to `runs/<id>/` with both source PDFs, the sheet and the
JSON record, so a review can be reopened later.

It binds to `127.0.0.1` only and has no authentication — it is a desk tool, not a
service, and the documents it handles are usually confidential. It is built on
`http.server` from the standard library, so it adds no dependency.

## AI assistance (optional, off by default)

The parser only recognises the table layout it was built for and refuses anything
else. That is right for a known template and useless for a document someone has just
uploaded — which is exactly the gap a model can fill without being trusted with any
judgement.

### Where the key goes

Get one at [build.nvidia.com](https://build.nvidia.com), then put it in a `.env`
file at the project root — that is the whole configuration step:

```bash
cp .env.example .env
# then edit .env:  NVIDIA_API_KEY=nvapi-...
```

`.env` is gitignored, so the key stays out of the repository, out of terminal
scrollback and out of shell history. It is read fresh on every call rather than
once at startup, so the upload server picks up a new key without being
restarted — save the file and reload the page.

An exported `NVIDIA_API_KEY` environment variable works too and takes precedence,
for CI or a container where that is the natural place for it.

Check it before you rely on it:

```bash
./.venv/bin/python -m protocolqc.ai.check
```

That makes one real call, then confirms the model's quote can be found in the
source document and that a fabricated quote is refused. It is not part of the
test suite on purpose — a suite that needs a key and a network is a suite nobody
runs — so this is the only thing here that touches the live API.

### Using it

```bash
./.venv/bin/python run.py --protocol a.pdf --report b.pdf --ai
./.venv/bin/python run.py --protocol a.pdf --report b.pdf --ai --ai-suggest
./.venv/bin/python run.py ... --ai --ai-model nvidia/llama-3.1-nemotron-70b-instruct
```

| flag | what the model is allowed to do |
| --- | --- |
| `--ai` | **Locate structure** in a document the parser declined. It returns quoted text and a line number; the tool then finds that text in your document and builds the offsets itself. Anything it cannot point at verbatim is discarded. |
| `--ai-suggest` | **Raise advisory observations** about differences the rules do not model. Kept in their own list, never merged into the findings, and dropped outright if their quotes are not in the source or if they use pass/fail language. |

What the model is never allowed to do: run the checks, supply a character offset,
decide pass or fail, or have text shown to a reviewer that was not first found in the
source document. Rules stay deterministic either way, and the citation gate applies to
model output exactly as it applies to rule output.

Without a key, both flags warn and the run continues — the deterministic checks are
unaffected. The client is built on `urllib`, so this adds no dependency either.

Every run that uses a key prints which one, masked (`nvapi-...1234`) and with the
place it was found. Enough to tell two keys apart in a log, never enough to use one.

## What it found in the samples

16 findings: 9 high, 4 medium, 3 low. Five further checks ran and found nothing,
which is reported too.

| # | Where | What |
| --- | --- | --- |
| R-01 | document | Report says it verifies protocol **v1.0**; the protocol supplied is **v2.0** |
| R-04 | document | Instron calibration **due 30 June 2025**, report dated **3 July 2026** — over a year out of calibration |
| R-06 | document | Report never states when testing actually happened, so calibration currency cannot be confirmed |
| R-10 | T5 | **Cytotoxicity is missing entirely.** Protocol requires T1–T5; report contains T1–T4 |
| R-12 | T1 | Report prints the criterion as **≥ 4.5 N**; the protocol requires **≥ 5.0 N** — a weakened criterion |
| R-13 | T1 | **25 units tested**, protocol requires **30** |
| R-14 | T1 | Reported minimum **4.7 N** is below the protocol's **≥ 5.0 N** |
| R-14 | T3 | Reported **0.45 N** is above the protocol's **0.20 – 0.40 N** range |
| R-15 | T1, T3 | Both recorded as **"Pass"** while their own recorded values sit outside the protocol criterion |
| R-16 | T1 | Tested at **ambient / room temperature**; protocol requires a **37 °C saline bath** |
| R-17 | document | Multiple departures from the protocol, and **no deviation recorded anywhere** — the protocol requires them documented and justified |
| R-18 | T5 | Protocol gives no numeric sample size for T5 (a gap in the protocol itself) |
| R-20 | document | Summary claims *"All tests reported are considered to meet their criteria"* |
| R-21 | document | Conclusion recommends **release** with T5 unreported and T1/T3 contested |
| R-22 | T4 | Criterion says *"at 24 h"*; the result does not evidence the 24 h point |

T2 raises nothing. It is consistent with the protocol on criterion, sample size and
result, and the tool says so rather than staying silent about it.

## The corrected pair

`corrected/` holds a revised protocol and report in which all 16 findings are resolved.
The same tool, unchanged, reports **0 findings** on them — with 18 checks recording that
they ran and had nothing to raise, which is what shows the 16 above are responses to the
documents rather than a tool that always fires.

```bash
./.venv/bin/python run.py \
    --protocol corrected/corrected-a-test-protocol-nv-200.pdf \
    --report   corrected/corrected-b-verification-report-nv-200.pdf \
    --out out/corrected
```

They are **fixtures, not remediation**. Most of these findings cannot be closed by
editing a document — T1 was run at ambient on 25 units and T5 was never reported, so
closing those means re-testing, not rewording. [CORRECTIONS.md](CORRECTIONS.md) maps
every finding to what changed and to how it would actually be closed in practice.
Regenerate them with `./.venv/bin/python fixtures/make_corrected.py`.

## The review sheet

`out/review-sheet.html` is the reviewer's working surface: **one self-contained file**, no
CDN, no fonts fetched, no network calls at all. It opens from a USB stick on a locked-down
machine. `test_page_is_self_contained` fails the build if a `<link>`, a `src=`, an
`@import` or a `fetch(` ever appears in it.

- **Evidence first.** Every flag shows the protocol text and the report text it came from,
  side by side, protocol on the left — the requirement, then what was recorded against it —
  each with the page and line to look up in the PDF. Panels are open by default.
- **Work it with the keyboard.** <kbd>j</kbd>/<kbd>k</kbd> move between findings,
  <kbd>1</kbd>–<kbd>4</kbd> record a decision, <kbd>e</kbd> toggles evidence,
  <kbd>/</kbd> searches (across quoted text as well as finding text).
- **Filter and search** by priority, scope (T1–T5 or document-level), and whether you have
  decided yet. Cards animate to their new positions rather than jumping, so you do not lose
  your place.
- **Three tabs**, because silence has to be legible: *Findings*, *Checks that ran* (all 19
  rules and what each concluded), and *Not checked* (the published blind spots).
- **Decisions are yours.** Four states per finding plus a rationale field, progress in the
  header, and an export to JSON stamped with the run and the input hashes. The tool never
  fills these in.
- Light and dark themes, a print stylesheet, and full `prefers-reduced-motion` support.

The interface needs JavaScript. When it is off, a `<noscript>` block states the counts and
the boundary and points at `findings.json` — which stays the audit record and needs no
browser at all.

## How it works

```
PDF ──ingest──► Document ──extract──► ParsedDoc ──rules──► Findings ──verify──► render
                (text with            (header fields,      (19 checks)   (gate)    (HTML + JSON)
                 page/line/col         sections, test
                 addressing)           table)
```

| module | job |
| --- | --- |
| `ui/` | the review sheet's interface — React + Framer Motion, built into `protocolqc/assets/` |
| `server.py` | local upload app (stdlib `http.server`) — same pipeline as the CLI |
| `pipeline.py` | one review end to end, shared by the CLI and the server so they cannot drift |
| `ai/client.py` | NVIDIA NIM over `urllib`; no key means the feature is simply off |
| `ai/locate.py` | **the AI safety boundary** — finds model-quoted text in the real document and builds the Span from what it finds |
| `ai/extract.py` | model-assisted extraction for layouts the parser declines |
| `ai/suggest.py` | advisory observations, gated and quarantined |
| `ingest.py` | PDF → text, using pypdf **layout mode** so table columns keep their positions |
| `model.py` | `Span` (an address + the exact characters there), `Citation`, `Finding`, `Document` |
| `table.py` | recovers the test table by finding *gutters* — columns blank on every row |
| `extract.py` | header fields, sections, and the test table as structured rows |
| `normalize.py` | criterion text → comparable values (`≥ 5.0 N`, `0.20 – 0.40 N`), result text → measurements |
| `rules.py` | the 19 checks; each returns findings **and** records that it ran |
| `verify.py` | re-reads every citation from source and aborts the run if one does not match |
| `quotes.py` | closes PDF layout artefacts in *displayed* quotes, licensed by a second extraction |
| `limits.py` | publishes what the tool did **not** check |
| `render.py` | inlines the built UI, the styles and the findings data into one file; writes the JSON audit record |

### The three design decisions that matter

**1. Citations are addresses, not strings.** A `Span` is `(page, line, columns)` plus
the characters found there. Quotes shown to a reviewer are rendered *from* spans, so
there is no code path that can display text the document does not contain. Before any
output is written, `verify.py` re-reads all 56 spans from the source and aborts the
whole run if a single one disagrees. This is not theoretical — the gate rejected three
of my own citations the first time it ran, and all three were real bugs.

**2. Results are compared against the protocol's criterion, never the report's.**
The report restates T1's criterion as ≥ 4.5 N. Compare 4.7 N against that and it looks
fine, which is exactly how a weakened criterion escapes review. Everything is compared
against the protocol's figure. There is a mutation test that pins this behaviour
(`test_results_are_judged_against_the_protocol_not_the_report`).

**3. Silence is reported, not implied.** Every rule records an outcome even when it
finds nothing, and the run publishes its own blind spots. A reviewer can tell
"checked, nothing to raise" from "never looked", which an empty findings list cannot.

### Where the tool says it is not sure

T1's protocol criterion is `≥ 5.0 N` with a sample size of 30, and the protocol never
says whether that applies to each unit or to the sample mean. The reported minimum
(4.7 N) is below it; the reported mean (6.1 N) is above it. The tool raises the
finding, states the ambiguity, and leaves it to the reviewer, rather than picking a
reading and sounding confident about it.

## How it is checked

99 tests, in seven groups:

- **`test_ingest.py`** — columns are recovered correctly, wrapped cells are rejoined
  (including the mid-word hyphen wrap `Per ISO 10993-` / `5`), and a table it does not
  recognise raises rather than being guessed at.
- **`test_citations.py`** — every span matches the source character for character; a
  fabricated quote, a quote at the wrong address, and a citation to an unknown
  document are each rejected by the gate.
- **`test_findings.py`** — the 16 expected discrepancies, written down from reading
  the PDFs by hand before the rules existed. Also asserts T2 stays clean, and that no
  finding uses verdict language.
- **`test_mutations.py`** — 16 tests that change the source text and check the rules
  respond: fix the version and R-01 falls silent; push T2's result out of spec and
  R-14 fires on T2. A rule that only ever fires on one known pair of documents proves
  nothing.
- **`test_corrected.py`** — the corrected pair raises nothing, *and* every rule reached
  a real comparison to get there. A parse failure would also produce zero findings, so
  "no findings" alone is not asserted anywhere.
- **`test_render.py`** — the sheet stays self-contained, the embedded data round-trips to
  the same payload as `findings.json`, and document text containing `</script>` cannot
  break out of the JSON block.
- **`test_ai.py`** — 21 tests, all offline against a stub client. An invented quote is
  refused, a wrong line number is corrected rather than trusted, a Span carries the
  document's characters and not the model's, model-extracted cells still pass the
  citation gate, a suggestion using pass/fail language is dropped, and a document the
  parser accepts never reaches the model at all.

Exit code is 0 whether or not findings were raised, and non-zero only when the tool
itself failed. An exit code that encoded "clean" would be a pass/fail verdict by the
back door.

## Known limits

- Built against this template family: a header block of `Key: value` lines, numbered
  sections, and one test table with a `Test ID` column. A differently shaped document
  raises `TableParseError` rather than producing wrong output.
- Condition checking compares stated temperature and named instrument only. Everything
  else in the method column is listed under "what was not checked".
- Scanned PDFs have no text layer and are out of scope; there is no OCR.
- It compares two documents. It has not seen the raw data behind either.

See `NOTES.md` for the build decisions, and what I changed or rejected from what the
AI first suggested.
