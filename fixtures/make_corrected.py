#!/usr/bin/env python3
"""Generate the corrected pair of synthetic documents.

These are FIXTURES, not remediation. Most of the discrepancies in the original
sample report cannot be closed by editing a document -- T1 was run at ambient
on 25 units and T5 was never reported, so closing those means re-testing, not
rewording. What this script produces is the pair of documents you would expect
to see *after* that work: a protocol revision that fills the one gap on the
protocol side, and a report of a verification that actually followed it.

Their purpose is to prove a negative. Run protocolqc against them and it goes
quiet, which is the only way to show that the 16 findings on the original pair
are responses to the documents rather than a tool that always fires.

Both documents carry the same "fictional / synthetic fixture" marking as the
originals and describe a device that does not exist.

    ./.venv/bin/python fixtures/make_corrected.py
"""

from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "corrected"

# Helvetica's built-in encoding has no glyph for the comparison operators, and
# the acceptance criteria have to be reproduced exactly -- rendering ">= 5.0 N"
# where the protocol says "≥ 5.0 N" would make the fixture test the wrong thing.
FONT_DIR = Path("/System/Library/Fonts/Supplemental")
REGULAR, BOLD = "DocFont", "DocFont-Bold"

PAGE_W, PAGE_H = A4
LEFT, RIGHT, TOP = 57.0, 538.0, 790.0
BODY_SIZE, TABLE_SIZE = 9.5, 8.5
LEADING = 13.0

# Column x positions. The gap between columns has to survive being turned back
# into characters by the layout extractor, so cell text is wrapped to stop
# GUTTER points short of the next column -- see wrap_cell().
COLUMNS = [57.0, 112.0, 232.0, 352.0, 404.0]
GUTTER = 14.0


def register_fonts() -> None:
    pdfmetrics.registerFont(TTFont(REGULAR, str(FONT_DIR / "Arial.ttf")))
    pdfmetrics.registerFont(TTFont(BOLD, str(FONT_DIR / "Arial Bold.ttf")))


def wrap(text: str, width: float, font: str, size: float) -> list[str]:
    lines, current = [], ""
    for word in text.split():
        trial = f"{current} {word}".strip()
        if current and pdfmetrics.stringWidth(trial, font, size) > width:
            lines.append(current)
            current = word
        else:
            current = trial
    if current:
        lines.append(current)
    return lines or [""]


def wrap_cell(text: str, index: int, size: float) -> list[str]:
    right = COLUMNS[index + 1] if index + 1 < len(COLUMNS) else RIGHT + 2
    return wrap(text, right - COLUMNS[index] - GUTTER, REGULAR, size)


class Doc:
    def __init__(self, path: Path):
        self.c = canvas.Canvas(str(path), pagesize=A4)
        self.y = TOP

    def line(self, text: str, x: float = LEFT, font: str = REGULAR,
             size: float = BODY_SIZE, gap: float = LEADING) -> None:
        self.c.setFont(font, size)
        self.c.drawString(x, self.y, text)
        self.y -= gap

    def blank(self, gap: float = LEADING * 0.7) -> None:
        self.y -= gap

    def paragraph(self, text: str, x: float = LEFT) -> None:
        for ln in wrap(text, RIGHT - x, REGULAR, BODY_SIZE):
            self.line(ln, x)

    def bullet(self, text: str) -> None:
        self.c.setFont(REGULAR, BODY_SIZE)
        self.c.drawString(LEFT + 18, self.y, "●")
        for i, ln in enumerate(wrap(text, RIGHT - LEFT - 36, REGULAR, BODY_SIZE)):
            self.line(ln, LEFT + 33)

    def field(self, key: str, value: str) -> None:
        self.c.setFont(REGULAR, BODY_SIZE)
        self.c.drawString(LEFT, self.y, f"{key}:")
        self.c.drawString(LEFT + 92, self.y, value)
        self.y -= LEADING

    def heading(self, text: str) -> None:
        self.blank(6)
        self.line(text, font=BOLD, size=BODY_SIZE + 0.5)

    def table(self, header: list[str], rows: list[list[str]]) -> None:
        self.blank(4)
        self.c.setFont(BOLD, TABLE_SIZE)
        for i, label in enumerate(header):
            self.c.drawString(COLUMNS[i], self.y, label)
        self.y -= TABLE_SIZE + 4
        self.c.setLineWidth(0.4)
        self.c.line(LEFT, self.y + 3, RIGHT, self.y + 3)
        self.y -= 4

        self.c.setFont(REGULAR, TABLE_SIZE)
        for row in rows:
            wrapped = [wrap_cell(cell, i, TABLE_SIZE) for i, cell in enumerate(row)]
            for offset in range(max(len(w) for w in wrapped)):
                for i, cell_lines in enumerate(wrapped):
                    if offset < len(cell_lines):
                        self.c.drawString(COLUMNS[i], self.y, cell_lines[offset])
                self.y -= TABLE_SIZE + 2.5
            self.y -= 2.5

    def save(self) -> None:
        self.c.showPage()
        self.c.save()


BANNER = "Meridian Neurovascular (fictional) — synthetic fixture for interview use only"

PROTOCOL_TESTS = [
    ["T1", "Tensile bond strength", "≥ 5.0 N", "30",
     "Tensile pull to failure in 37°C saline bath; Instron 5943"],
    ["T2", "Coating particulate", "≤ 20 particles ≥10 µm per unit", "30",
     "Particulate count per USP <788> adaptation"],
    ["T3", "Tip flexibility (bend force)", "0.20 – 0.40 N", "30",
     "3-point bend, 37°C saline"],
    ["T4", "Corrosion resistance", "No visible corrosion at 24 h", "10",
     "Immersion + potentiodynamic scan"],
    ["T5", "Cytotoxicity (biocompatibility)", "Reactivity grade ≤ 2", "3",
     "Per ISO 10993-5; reference to biocompatibility report BC-NV200-03"],
]

# Acceptance criteria are copied from PROTOCOL_TESTS rather than retyped, so
# the fixture cannot drift from the protocol it is meant to satisfy.
CRITERION = {row[0]: row[2] for row in PROTOCOL_TESTS}
SAMPLE_SIZE = {row[0]: row[3] for row in PROTOCOL_TESTS}

REPORT_RESULTS = {
    "T1": "Min 5.3 N, mean 6.4 N. Tested in 37°C saline bath. Pass.",
    "T2": "Max 12 particles. Pass.",
    "T3": "Range 0.24 – 0.36 N, mean 0.30 N. Tested at 37°C. Pass.",
    "T4": "No visible corrosion at 24 h. Pass.",
    "T5": "Reactivity grade 1. Pass.",
}


def build_protocol(path: Path) -> None:
    d = Doc(path)
    d.line("TEST / VERIFICATION PROTOCOL", font=BOLD, size=12)
    d.line(BANNER, size=8.5)
    d.blank(4)
    d.field("Document", "NV-200-TP-014")
    d.field("Title", "Design Verification Test Protocol — NeuroFlow NV-200 Access Guidewire")
    d.field("Version", "2.1")
    d.field("Effective", "1 June 2026")
    d.blank()

    d.heading("1. Purpose")
    d.paragraph(
        "To verify that the NeuroFlow NV-200 access guidewire meets its design inputs through "
        "the tests defined below. Acceptance criteria are derived from the approved design input "
        "requirements. This protocol is the reference against which the verification report "
        "NV-200-VR-014 is assessed."
    )

    d.heading("2. General requirements")
    d.bullet("All measuring instruments must be within current calibration at the time of testing.")
    d.bullet("Unless stated otherwise, samples are drawn per the sampling plan and tested under "
             "the conditions specified per test.")
    d.bullet("Any deviation from this protocol must be documented and justified in the "
             "verification report.")

    d.heading("3. Tests and acceptance criteria")
    d.table(["Test ID", "Test", "Acceptance criterion", "Sample size", "Method / conditions"],
            PROTOCOL_TESTS)

    d.heading("4. Reporting")
    d.paragraph(
        "Results for all five tests (T1 to T5) shall be recorded in verification report "
        "NV-200-VR-014, which must reference this protocol version. A human reviewer determines "
        "pass or fail against the criteria above."
    )

    d.heading("5. Revision history")
    d.paragraph(
        "Version 2.1, effective 1 June 2026. The sample size for T5 is stated as a number "
        "(3 units, per ISO 10993-5); in version 2.0 that column carried only a standard "
        "reference, leaving the required quantity undefined. The standard reference has moved "
        "to the method column. No acceptance criterion, test method or sample size for T1 to T4 "
        "was changed by this revision."
    )
    d.save()


def build_report(path: Path) -> None:
    d = Doc(path)
    d.line("DESIGN VERIFICATION REPORT", font=BOLD, size=12)
    d.line(BANNER, size=8.5)
    d.blank(4)
    d.field("Document", "NV-200-VR-014")
    d.field("Title", "Design Verification Report — NeuroFlow NV-200 Access Guidewire")
    d.field("Revision", "2.0")
    d.field("Verifies protocol", "NV-200-TP-014, Version 2.1")
    d.field("Testing performed", "15 to 19 June 2026")
    d.field("Date", "24 July 2026")
    d.field("Test equipment", "Instron 5943 (serial 5943-11); calibration due 31 March 2027")
    d.blank()

    d.heading("1. Summary")
    d.paragraph(
        "Verification testing of the NeuroFlow NV-200 access guidewire was carried out between "
        "15 and 19 June 2026 against the acceptance criteria of NV-200-TP-014 Version 2.1. All "
        "five tests defined by that protocol were performed at the sample sizes and under the "
        "conditions it specifies. Results are recorded in section 2. A human reviewer determines "
        "pass or fail against the protocol criteria."
    )

    d.heading("2. Results")
    d.table(["Test ID", "Test", "Acceptance criterion", "n tested", "Result and disposition"],
            [[row[0], row[1], CRITERION[row[0]], SAMPLE_SIZE[row[0]], REPORT_RESULTS[row[0]]]
             for row in PROTOCOL_TESTS])

    d.heading("3. Deviations")
    d.paragraph(
        "No deviation from NV-200-TP-014 Version 2.1 arose during this verification. Sample "
        "sizes, test conditions, instrumentation and acceptance criteria were as specified by "
        "the protocol. This section is recorded as nil rather than omitted, so that its absence "
        "cannot be read as an oversight."
    )

    d.heading("4. Conclusion")
    d.paragraph(
        "Results for all five tests required by NV-200-TP-014 Version 2.1 are recorded above "
        "against the acceptance criteria of that protocol version, with the raw data held in "
        "the design history file. Disposition of each test, and any decision on release to the "
        "next design phase, rests with the reviewer and the design team."
    )
    d.save()


def main() -> None:
    register_fonts()
    OUT.mkdir(exist_ok=True)
    protocol = OUT / "corrected-a-test-protocol-nv-200.pdf"
    report = OUT / "corrected-b-verification-report-nv-200.pdf"
    build_protocol(protocol)
    build_report(report)
    print(f"wrote {protocol}\nwrote {report}")


if __name__ == "__main__":
    main()
