# Build notes — decisions, and what I changed or rejected

Brief record of the choices behind `protocolqc`, including the points where the first
approach the AI reached for was wrong and got replaced. Ordered roughly by how much
they matter.

---

## 1. No LLM in the comparison path

**First suggestion:** put both documents in a prompt and ask a model to list the
discrepancies with quotes.

**Rejected, for four reasons:**

- It paraphrases. A model asked for a quote will produce something close to the text
  rather than the text. In a regulated review, a citation that is nearly right is the
  worst possible output — it looks checkable and isn't.
- It is not reproducible. Two runs give different findings, so nothing can be
  regression-tested and no run can be reproduced for an auditor.
- It cannot show its work. "Why did it flag this?" has no answer beyond the model's
  output. `R-13` has an answer: 25 < 30, here are both numbers and where they are.
- Silence means nothing. If the model returns four findings you cannot tell whether it
  checked for the other twelve.

**What replaced it:** deterministic rules over a structured extraction, every quote
addressed by `(page, line, columns)` and re-read from the source before output.

**Where an LLM would genuinely earn its place** (see §11, now built): the extraction layer, for
documents whose layout the parser does not recognise — proposing *where* the fields
are, then handing back offsets that go through the same verbatim gate. The judgement
stays deterministic; the model only helps find the text.

## 2. Compare against the protocol's criterion, never the report's

The report restates T1's acceptance criterion as **≥ 4.5 N**. The protocol requires
**≥ 5.0 N**. The reported minimum is **4.7 N**.

The obvious implementation — check each row's result against the criterion printed in
that row — reports T1 as fine. That is precisely the mechanism by which a weakened
criterion passes review unnoticed, and it is the single most consequential decision in
the codebase. `R-14` reads the criterion from the protocol and only from the protocol,
and `R-12` separately flags that the two documents disagree about what the criterion
is. There is a mutation test whose only job is to pin this
(`test_results_are_judged_against_the_protocol_not_the_report`): change the *protocol*
to ≥ 4.5 N and R-14 correctly falls silent for T1.

## 3. Layout-mode extraction, and columns from gutters

**First approach:** `page.extract_text()`, then regex the rows.

That flattens the table into run-on text:

```
T1 Tensile bond strength ≥ 5.0 N 30 Tensile pull to failure in 37°C saline bath; Instron 5943
```

Finding where the criterion ends and the sample size begins means guessing, and it
breaks outright on the two cells that wrap: T2's criterion (`≤ 20 particles ≥10 µm per`
/ `unit`) and T5's sample size (`Per ISO 10993-` / `5`).

**Replaced with** `extraction_mode="layout"`, which keeps x-positions, so the columns
survive.

**Second correction, within that:** the natural next step is to slice each row at the
character offsets of the header labels. That breaks the moment a data cell starts
slightly left of its header. Columns are instead found by *gutters* — positions blank
on **every** line of the table block. It is derived from the table's own geometry, and
it handles wrapped cells for free, because a continuation line has a blank Test ID
column.

## 4. Refuse rather than guess

If the table headers are not recognised, or there are no `T`-numbered rows,
`table.py` raises `TableParseError` and the CLI exits non-zero having written nothing.
A tool that silently mis-parses a table is worse than one that stops, because its
output still looks authoritative. Tested in
`test_unrecognised_table_is_refused_not_guessed`.

## 5. The tool must not decide pass or fail — enforced, not just intended

Stated as a boundary it drifts. So it is built in:

- `Finding` has no pass/fail field. It carries an *observation*, the requirement that
  makes it checkable, and an action for the reviewer.
- Findings are phrased "the report records X, the protocol requires Y" — never "T1
  fails". `test_no_finding_states_a_verdict` scans every finding for verdict language
  and fails the build if it appears.
- Priority is `high/medium/low` **review priority** — a suggested reading order. An
  earlier draft used `critical/major/minor`, which reads as a severity classification
  and pulls toward a verdict.
- The exit code is 0 whether or not findings were raised. An exit code that meant
  "clean" would be a verdict by the back door, and CI would start treating it as one.
- `R-15` is the closest call in the ruleset: it observes that a row recorded "Pass"
  carries values outside the protocol criterion. That is a documented internal
  inconsistency, not an adjudication, and it is worded to stay on that side of the
  line.

## 6. The citation gate found three of my own bugs

`verify.py` re-reads every span before anything is written. On its first run it
rejected three citations, and all three were genuine defects:

- **R-17** built a citation from three non-contiguous section headings, then checked
  the joined string against the page — which of course isn't there.
- **R-18** and the T5 limit joined a wrapped cell into `"Per ISO 10993- 5"`, a string
  that appears in neither document.

**First instinct was to loosen the check** so the run would complete. That is exactly
backwards: the check was right and the citations were wrong. Two changes followed:
verification is **per span** rather than per assembled quote (a citation may
legitimately gather non-contiguous pieces), and multi-line quotes are joined with a
line break rather than a space, so nothing is presented as continuous prose when it
isn't.

## 7. Repairing display quotes only where a second extraction licenses it

Layout mode reconstructs spacing from glyph positions, and in justified paragraphs
that opens gaps inside words: the report's summary came out as
`"All tests reported are con sidered to meet their criteria."` Faithful, and it
destroys reviewer confidence in every other quote on the page.

**Rejected:** collapsing spaces heuristically. `per unit` → `perunit` is the same
transformation, and quietly corrupting a quote is the failure this whole design exists
to prevent.

**Built instead:** pypdf's default extraction reads the same file's character stream
without using positions, and renders that word correctly. A space is closed **only**
when the joined form occurs as a whole word in that second extraction *and* the two
pieces do not also occur separately there. The raw span text is untouched, still what
the gate verifies, and the JSON records both forms with a
`display_differs_from_source` flag. It can only ever remove a space, never add or
change a character.

## 8. Smaller calls

- **Mean excluded from the conformity comparison** (`worst_case`). A mean of 6.1 N
  cannot demonstrate that every unit met ≥ 5.0 N. But it is still *reported*, because
  the protocol does not say whether the criterion is per-unit or on the mean — so the
  finding states the ambiguity and hands it over rather than picking a side. "I am not
  sure, and here is exactly what is unclear" is the right output here.
- **Citing an absence.** You cannot quote text that isn't there. `R-17` cites the
  protocol clause requiring deviations to be documented, plus the report's actual
  section headings as evidence of what the report *does* contain. `R-10` cites every
  Test ID the report's table carries.
- **`R-18` flags the protocol, not the report.** T5's sample size reads
  "Per ISO 10993-5" — the brief is report-versus-protocol, but a protocol gap that
  makes a check impossible is worth a reviewer's attention, at low priority.
- **`R-04` states its assumption.** The report gives no test date, so the report date
  is used as a proxy for "time of testing" and the finding says so. `R-06` separately
  flags the missing test date.
- **Negative controls are output.** R-02, R-03, R-05, R-11 and R-19 ran and found
  nothing; the review sheet lists them. T2 is consistent on all counts and raises
  nothing — a run that flagged it would be wrong, which is why
  `test_t2_is_clean` exists.

## 9. The corrected pair, and the one tool change it forced

`corrected/` holds a revised protocol and report where all 16 findings are resolved, and
the tool goes quiet on them. That fixture is what makes the 16 findings meaningful — on
its own, a tool that reports discrepancies could just be a tool that always reports
discrepancies.

**Rejected on the way:** simply retyping the report's numbers to match the protocol. In
a regulated setting that is not a correction, it is a falsification. T1 was run at
ambient on 25 units and T5 was never performed; those close by re-testing or by a
justified deviation, not by editing. The fixture is built as the pair you would expect
*after* that work, and `CORRECTIONS.md` carries a column for how each finding would
really be closed. It also needed a **protocol** revision, not just a report one — R-18
is a gap in the controlled document the report is measured against.

**The check that nearly passed for the wrong reason.** The first corrected pair produced
0 findings, which is what I wanted, and that is exactly why it needed a second look. Two
of them were undeserved: R-14 had compared T1, T2, T3 and skipped T4 and T5 without
raising anything. T4 is legitimate — its criterion is qualitative and R-22 covers it.
T5 was not: "Reactivity grade 1" states neither a minimum nor a maximum, so
`parse_measurements` found no value at all and the test was silently uncompared. The
fixture would have shown T5 present with its result never actually checked.

`parse_measurements()` now also takes the criterion's own label — "Reactivity grade"
from "Reactivity grade ≤ 2" — and matches values stated that way. It changes nothing on
the original pair, where T5 has no result to parse. The general lesson is the one the
whole design is built around: a check that finds nothing and a check that never ran look
identical from the outside, which is why every rule reports its own outcome and why
`test_corrected.py` asserts *how* the silence was reached rather than just that it was.

## 10. The interface, and where the design tool was wrong

The review sheet is a React + Framer Motion app, built from `ui/` and inlined by
`render.py`. The design system came from the ui-ux-pro-max skill; the motion vocabulary
from the framer-motion skill. Both needed correcting.

**Where the design tool was wrong.** The first `--design-system` query read "review sheet"
as *product reviews and ratings* and returned a **Product Review/Ratings Focused** pattern
in an **Exaggerated Minimalism** style — `font-size: clamp(3rem, 10vw, 12rem)`,
`font-weight: 900`, "massive whitespace". That is a luxury-brand landing page. Applied to a
sixteen-finding audit worksheet it would be actively harmful: a QA reviewer needs to
compare quoted text across two documents, not read a headline.

Rejected and re-queried the product domain directly, which returned the right analogue:
**E-signature / Document Workflow** — "Trust & Authority + Minimalism", *Document Pipeline
Dashboard*, palette "trust navy + signature green + pending amber + neutral grey". That
palette is what shipped. Two other things I kept from the tool: the density dial at 8/10
(8–32px spacing, dashboard-tight rather than marketing-airy) and its type scale.

**Rejected: the recommended webfont.** The typography match (EB Garamond / Lato, "legal,
contracts, formal documents") suits the domain, but it arrives as a Google Fonts CDN
`@import`. This page has to open from a file path on a machine with no network, so a
webfont is not a style choice, it is a broken page. System stack instead. Monospace is kept
for document quotes because the extracted text is column-aligned and that alignment is
meaningful.

**The self-containment constraint drove the build.** Framer Motion means React, and React
means a bundler. esbuild bundles everything — React, Framer Motion, the app, the CSS — into
two committed assets that `render.py` inlines alongside the findings JSON. One file,
~410 KB, zero requests. `test_page_is_self_contained` fails the build if a `<link>`,
`src=`, `@import` or `fetch(` ever appears, and `test_document_text_cannot_break_out_of_the_json_block`
pins the `\u003c` escaping that stops a PDF containing `</script>` from ending the tag
early. Node is needed to build the UI; it is not needed to run the tool.

**Rejected: progressive disclosure of the evidence.** The first build had citation panels
collapsed, which is the textbook rule for dense interfaces and wrong here. The quoted text
*is* the reason to trust a flag — hiding it behind a click makes the tool assertive rather
than evidential. Evidence is open by default, with collapse-all for scanning. Citations are
also reordered protocol-first, so every card reads as requirement then observation.

**Motion is subordinate to the task.** Stagger on first paint, layout animation so cards
slide rather than jump when a filter changes, `layoutId` for the filter and tab indicators
so the selection travels instead of blinking, spring-driven collapse for evidence. Exit
transitions are faster than entrances. `useReducedMotion` strips every translate and scale
while keeping the state change, and the stylesheet carries a `prefers-reduced-motion` block
as a second line of defence. Nothing animates `width` or `height` directly.

**Two smaller calls.** Keyboard first — <kbd>j</kbd>/<kbd>k</kbd>, <kbd>1</kbd>–<kbd>4</kbd>,
<kbd>e</kbd>, <kbd>/</kbd> — because a reviewer works through sixteen of these in a sitting.
And `localStorage` is not guaranteed on a `file://` origin: the old sheet would have thrown
on every keystroke if it were blocked, whereas the app now degrades to session-only and
tells the reviewer to export before closing the tab.

**The cost, stated plainly.** The sheet now requires JavaScript, which the previous static
HTML did not. The `<noscript>` block gives the counts and the boundary and points at
`findings.json`, which remains the audit record and needs no browser — but if you care more
about a document that renders anywhere than about the interface, the old renderer was
better on that one axis.

## 11. Upload, and putting a model where it earns its place

Two requests arrived together — let users upload their own documents, and integrate
NVIDIA's API — and they turn out to be the same problem. The parser recognises one
table layout and refuses everything else (§4). That is correct for a known corpus and
useless the moment a stranger uploads a document. Locating structure in an unfamiliar
layout is precisely the job §1 identified as the one an LLM should have here.

**§1 still stands.** The model does not run the checks. It is not asked whether
anything conforms. Every rule in `rules.py` is untouched, and a document the
deterministic parser accepts never reaches the model at all — there is a test for
that, `test_deterministic_documents_never_reach_the_model`.

**The boundary is one function.** `ai/locate.py` is the entire safety story. The model
returns a quote and a line number; it never returns a character offset. `locate()`
searches the document for that text and builds the Span from what it actually finds.
A quote that is not in the document produces no Span, so it cannot reach a reviewer —
and `verify.py` then re-checks every survivor through the same path it uses for rule
citations. Three consequences worth stating:

- Matching is whitespace-flexible in one direction only. A model writing
  `"Version: 2.0"` matches the document's `"Version:  2.0"`, and the Span carries the
  **document's** characters, two spaces and all. Tested.
- A wrong line number is corrected, not trusted. Models miscount lines; the Span
  records where the text really is, so the citation stays true and the bad hint is
  counted in the run record.
- Invented content is dropped, never repaired. A hallucinated acceptance criterion
  leaves an empty cell, which the rules then report as missing — the honest outcome.

**Suggestions are quarantined, not integrated.** `--ai-suggest` addresses a real
documented weakness (§12: R-16 compares temperature and instrument and nothing else),
but its output is not a finding and must never look like one. It travels in a separate
`ai_suggestions` key, renders under its own heading with a dashed border, carries its
caveat on every card rather than once at the top, and is dropped entirely if its quotes
cannot be found.

**Rejected: trusting the prompt to enforce the boundary.** The suggestion prompt
forbids pass/fail language. Prompts are not controls, so `suggest()` also filters the
reply and drops anything that adjudicates. The first version of that filter had a real
hole — `fail(?:e[sd]|ure)?` does not match "fails", because `\b` fails on the trailing
`s` — and a test caught it. It is now prefix-based and deliberately over-broad: a
dropped suggestion costs nothing and is recorded in the notes, whereas an adjudication
shown to a reviewer is the failure that matters.

**Two dependencies I did not add.** The upload server is `http.server` from the
standard library and the NVIDIA client is `urllib`. Flask and the openai SDK would both
have been less code to write; the install story stays "python, one dependency", which
matters more for a tool meant to run on a locked-down QA machine. `cgi` was removed in
Python 3.13, so uploads arrive base64-encoded in a JSON body rather than as multipart.

**The CLI and the server share `pipeline.py`.** A difference in behaviour between "I
ran it on the command line" and "I uploaded it" would be indefensible in a regulated
setting, so there is one code path and both call it.

**What is not verified.** The AI path has 21 tests, all offline against a stub client,
and the live HTTP plumbing is confirmed against the real endpoint (correct URL and auth
header; 403 and 404 both produce clean, actionable errors). But **no inference call has
ever been made** — there is no NVIDIA API key in this environment. The gate is tested;
the model's actual behaviour on a real unfamiliar document is not. Before this went
anywhere near real work it would need a corpus of genuinely different layouts, a
measured rate of correct extraction, and a measured rate of suggestions that turn out
to be noise.

## 12. What I would do next, in order

1. **Reviewer sign-off as a first-class record.** Decisions currently live in browser
   `localStorage` with a JSON export. It should be a signed record: reviewer identity,
   timestamp, decision and rationale per finding, hash-linked to the input files and
   ruleset version already in the manifest.
2. **LLM-assisted extraction, same gate.** For documents this parser does not
   recognise, have a model propose field locations and return offsets, then run those
   offsets through `verify.py` unchanged. Anything it cannot point at in the source is
   discarded. That extends reach without moving judgement into the model. Findings
   sourced this way should be labelled as such in the output.
3. **Requirement-level traceability.** Join to design inputs, so coverage is checked
   against requirements rather than against the protocol's own test list.
4. **Highlight in the PDF.** The spans carry page/line/column; keeping the glyph
   coordinates too would let the sheet link straight to the highlighted text.
5. **Ruleset as reviewed configuration.** Rules are code today. Where a QA lead should
   be able to change thresholds and wording without a developer, they belong in a
   version-controlled config with its own approval trail.
6. **A proper corpus.** Two synthetic documents cannot tell you the false-positive
   rate. Before this went near real work it would need a body of real
   protocol/report pairs with known outcomes, and a measured miss rate.

## 13. Weak points, stated plainly

- Gutter-based column detection merges two columns if their text touches on *any* row.
  It would raise on the header check rather than mis-parse silently, but on a denser
  table it would refuse to run.
- `R-16` only compares stated temperature and named instrument. A method changed in
  any other way is not caught — it goes in "what was not checked", which is honest but
  is not detection.
- `R-22` ("at 24 h" not restated) and `R-06` are judgement calls. Some reviewers will
  call them noise. They are low priority for that reason, and dropping them is a
  one-line change.
- Priorities are my judgement, not a standard.
- Two synthetic documents, one page each. Nothing here is evidence of behaviour at
  scale.
