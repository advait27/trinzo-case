# Corrected document pair — what changed, and what a correction actually means

`corrected/` holds a revised protocol and report in which all 16 findings are resolved.
Running the tool against them produces **0 findings**, with 18 checks reporting that
they ran and had nothing to raise.

```bash
./.venv/bin/pip install -r fixtures/requirements.txt   # reportlab, for regeneration only
./.venv/bin/python fixtures/make_corrected.py          # regenerate the pair
./.venv/bin/python run.py \
    --protocol corrected/corrected-a-test-protocol-nv-200.pdf \
    --report   corrected/corrected-b-verification-report-nv-200.pdf \
    --out out/corrected
```

## Read this before using them

**Most of these findings cannot be closed by editing a document.** T1 was run at
ambient temperature on 25 units and produced a 4.7 N minimum; T5 was never reported at
all. Nothing about that is fixed by retyping the report — it is fixed by re-testing, or
by a documented and justified deviation that a reviewer accepts. A document whose
numbers were changed to match the protocol would not be a corrected report, it would be
a falsified one.

So these files are **fixtures, not remediation**: the pair you would expect to see
*after* the underlying work was redone. Their job is to prove a negative — that the 16
findings on the original pair are responses to those documents, and not a tool that
fires no matter what it is given. The column on the right of the table below is the
part that matters in practice.

Both documents carry the same "fictional / synthetic fixture for interview use only"
marking as the originals, and describe a device that does not exist.

## What changed, finding by finding

| Rule | Original | Corrected | How it would really be closed |
| --- | --- | --- | --- |
| R-01 | Report verifies protocol **v1.0**; protocol is **v2.0** | Report verifies **v2.1**; protocol is **v2.1** | Document control. Establish which version testing ran under; if it was v1.0, the results need re-assessing against the current one |
| R-04 | Calibration **due 30 Jun 2025**, report dated 3 Jul 2026 | Calibration **due 31 Mar 2027**, testing 15–19 Jun 2026 | **Re-test.** Data from out-of-calibration equipment is not usable, and no wording makes it so |
| R-06 | No date of testing anywhere | `Testing performed: 15 to 19 June 2026` | Genuine documentation fix — the dates exist in the raw records |
| R-10 | **T5 cytotoxicity absent** | T5 reported: reactivity grade 1, n = 3 | **Run the test**, or report the result from BC-NV200-03 with its data |
| R-12 | Report prints **≥ 4.5 N**; protocol requires **≥ 5.0 N** | Report prints **≥ 5.0 N** | Documentation fix — but the real question is which figure the original results were dispositioned against, and why the report carried a different one |
| R-13 | **25 units** tested; protocol requires 30 | **30 units** | Test the remaining units, or raise a justified deviation |
| R-14 (T1) | Minimum **4.7 N** against ≥ 5.0 N | Minimum **5.3 N**, mean 6.4 N | **Re-test.** This is the finding that cannot be edited away |
| R-14 (T3) | **0.45 N** against 0.20 – 0.40 N | Range **0.24 – 0.36 N** | Re-test, or investigate the outlier unit and disposition it explicitly |
| R-15 (T1, T3) | "Pass" recorded against out-of-spec values | Dispositions consistent with the values | Follows from the two above |
| R-16 | Tested at **ambient / room temperature**; protocol requires a 37 °C saline bath | Tested in **37 °C saline bath** | **Re-test under protocol conditions.** A change of test method, not of paperwork |
| R-17 | No deviation record at all | §3 Deviations, recorded explicitly as nil | Each departure needs a documented, justified deviation — or, as here, a positive statement that none arose |
| R-18 | Protocol's T5 sample size reads "Per ISO 10993-5" | Protocol **v2.1**: sample size `3`, standard reference moved to the method column | **Protocol revision through change control.** This one is on the protocol side, which is why the corrected pair needed a protocol revision as well |
| R-20 | Summary claims *"All tests reported are considered to meet their criteria"* | Summary states what was performed and leaves disposition to the reviewer | Rewording — legitimate only once the results actually support it |
| R-21 | Conclusion recommends **release** | Conclusion records the results; release rests with reviewer and design team | As above |
| R-22 | "No corrosion observed" — the 24 h point not evidenced | "No visible corrosion at 24 h" | Documentation fix from the raw records |

### Deliberately unchanged

- **T2** was already consistent on criterion, sample size and result, and is untouched.
- **Acceptance criteria for T1–T4** are unchanged. Correcting a report by loosening the
  protocol would be the same defect the tool was built to catch, pointed the other way.
- **Test methods** are unchanged. T1's corrected result comes from testing under the
  protocol's conditions, not from relaxing them.
- Criteria and sample sizes in the corrected report are **copied from the protocol
  definition in code**, not retyped, so the fixture cannot drift from the protocol it
  is supposed to satisfy.

## Why the protocol needed revising too

Fifteen findings are on the report. R-18 is not: the protocol's own sample-size column
for T5 reads "Per ISO 10993-5", a standard reference rather than a quantity, so the
number of units required is undefined and the check is impossible. That is a gap in the
protocol, and no version of the report can close it. Protocol **v2.1** states the
sample size as `3` and moves the standard reference to the method column, with the
change recorded in a revision-history section.

This is worth noticing on its own: the tool flagged a defect in the controlled document
that the report was being measured against.

## What is verified about the corrected pair

`tests/test_corrected.py` (13 tests) asserts more than "no findings", because a parse
failure would also produce no findings and would be the worst possible way to pass:

- both documents parse to the full five tests;
- every rule reached a **real comparison** — R-17 is the only "not applicable", and
  legitimately so, since there are no departures for it to look for;
- R-12 and R-13 compared all five tests, R-14 compared T1, T2, T3 and T5, R-22 covered
  T4;
- the blind-spots list is still published, so a clean run does not read as "everything
  is fine";
- and two mutations of the corrected report still fire: drop T1's minimum to 4.3 N and
  R-14/R-15 raise it; change T5's reactivity grade to 3 and R-14 raises that.

## One change to the tool

Making the fixture honest required a small addition to `normalize.py`. T5's result
reads "Reactivity grade 1" — it states neither a minimum nor a maximum, so the parser
found no value and R-14 skipped the test silently. The corrected report would then have
shown T5 as *present* while its result was never actually compared.

`parse_measurements()` now takes the criterion's own label ("Reactivity grade" from
"Reactivity grade ≤ 2") and matches values stated that way. It is covered by
`test_value_labelled_by_the_criterion_itself` and by the mutation above, and it changes
nothing on the original pair, where T5 has no result to parse in the first place.

## If these were real documents

A re-issued verification report is a controlled document. It would need change control,
re-approval, and retention of the superseded revision, and the deviation and re-test
records would sit alongside it in the design history file. Regenerating a PDF from a
script is a fixture-building convenience and nothing more.
