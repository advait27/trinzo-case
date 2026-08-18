"""Turn criterion and result *text* into comparable values.

Everything here is conservative: when a string cannot be parsed with
confidence it returns None, and the calling rule then reports that it could
not compare rather than inventing a comparison.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import List, Optional

from .model import normalise

MONTHS = {
    m: i
    for i, m in enumerate(
        ["january", "february", "march", "april", "may", "june", "july",
         "august", "september", "october", "november", "december"],
        start=1,
    )
}

NUM = r"[-+]?\d+(?:\.\d+)?"


# ---- acceptance criteria -----------------------------------------------

@dataclass
class Threshold:
    op: str  # ">=" | "<="
    value: float
    unit: str
    prefix: str = ""  # e.g. "reactivity grade"

    kind = "threshold"

    def outside(self, value: float) -> bool:
        return value < self.value if self.op == ">=" else value > self.value

    def describe(self) -> str:
        return f"{self.op} {self.value:g} {self.unit}".strip()


@dataclass
class Range:
    low: float
    high: float
    unit: str

    kind = "range"

    def outside(self, value: float) -> bool:
        return value < self.low or value > self.high

    def describe(self) -> str:
        return f"{self.low:g} - {self.high:g} {self.unit}".strip()


@dataclass
class Qualitative:
    text: str

    kind = "qualitative"

    def describe(self) -> str:
        return self.text


Criterion = Threshold | Range | Qualitative


def parse_criterion(text: str) -> Optional[Criterion]:
    """Parse an acceptance criterion. Range is tried before threshold because
    '0.20 - 0.40 N' contains no operator and would otherwise fall through."""
    if not text.strip():
        return None
    norm = normalise(text)

    m = re.search(rf"({NUM})\s*-\s*({NUM})\s*([a-zA-Z%µ°]*)", norm)
    if m and not re.search(r"[<>]=", norm):
        return Range(float(m.group(1)), float(m.group(2)), m.group(3).strip())

    m = re.search(rf"(>=|<=)\s*({NUM})\s*(.*)$", norm)
    if m:
        prefix = norm[: m.start()].strip(" .,:;")
        unit = m.group(3).strip()
        return Threshold(m.group(1), float(m.group(2)), unit, prefix)

    return Qualitative(text.strip())


# ---- reported results ---------------------------------------------------

@dataclass
class Measurement:
    """One number pulled out of a result cell, with the word that labelled it."""

    label: str  # "min" | "max" | "mean" | "range" | "observation"
    value: float
    unit: str
    source: str  # the exact substring it came from


LABELLED = re.compile(
    rf"\b(min|minimum|max|maximum|mean|average)\b[^0-9\-+]{{0,12}}({NUM})\s*([a-zA-Z%µ]*)",
    re.I,
)
RANGE = re.compile(rf"\brange\b[^0-9\-+]{{0,12}}({NUM})\s*[-–]\s*({NUM})\s*([a-zA-Z%µ]*)", re.I)
BARE_AT = re.compile(rf"\bat\s+({NUM})\s*([a-zA-Z%µ]*)", re.I)

_LABEL_CANON = {"minimum": "min", "maximum": "max", "average": "mean"}


def parse_measurements(text: str, prefix: str = "") -> List[Measurement]:
    """Numbers in a result cell, with the word that labelled each one.

    `prefix` is the criterion's own label where it has one -- "Reactivity
    grade" in "Reactivity grade <= 2". Results state such values by repeating
    that label ("Reactivity grade 1") rather than by saying min or max, so
    without it the value is never found and the test is silently not compared.
    """
    if not text.strip():
        return []
    src = text.replace("–", "-").replace("—", "-")
    out: List[Measurement] = []

    for m in RANGE.finditer(src):
        unit = m.group(3).strip()
        out.append(Measurement("min", float(m.group(1)), unit, m.group(0)))
        out.append(Measurement("max", float(m.group(2)), unit, m.group(0)))

    for m in LABELLED.finditer(src):
        label = _LABEL_CANON.get(m.group(1).lower(), m.group(1).lower())
        out.append(Measurement(label, float(m.group(2)), m.group(3).strip(), m.group(0)))

    # "(one unit at 0.45 N)" -- an individual observation called out in prose.
    for m in BARE_AT.finditer(src):
        val, unit = float(m.group(1)), m.group(2).strip()
        if unit and not any(o.value == val for o in out):
            out.append(Measurement("observation", val, unit, m.group(0)))

    # "Reactivity grade 1" against a criterion of "Reactivity grade <= 2".
    if prefix:
        for m in re.finditer(rf"{re.escape(prefix)}\s+({NUM})\s*([a-zA-Z%µ]*)", src, re.I):
            val = float(m.group(1))
            if not any(o.value == val for o in out):
                out.append(Measurement("observation", val, m.group(2).strip(), m.group(0)))

    return out


def worst_case(criterion: Criterion, values: List[Measurement]) -> List[Measurement]:
    """Measurements that could sit outside the criterion.

    For a '>=' criterion the risk is at the low end, for '<=' at the high end,
    for a range at both ends. Means are excluded from the comparison because a
    mean cannot demonstrate conformity of individual units -- but the caller
    still reports the mean so the reviewer sees the full picture.
    """
    relevant = [v for v in values if v.label != "mean"]
    if isinstance(criterion, Threshold):
        if criterion.op == ">=":
            return [v for v in relevant if v.label in ("min", "observation")]
        return [v for v in relevant if v.label in ("max", "observation")]
    if isinstance(criterion, Range):
        return relevant
    return []


# ---- misc ---------------------------------------------------------------

def parse_int(text: str) -> Optional[int]:
    m = re.fullmatch(r"\s*(\d+)\s*", text or "")
    return int(m.group(1)) if m else None


def parse_date(text: str) -> Optional[date]:
    m = re.search(r"\b(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})\b", text or "")
    if not m:
        return None
    month = MONTHS.get(m.group(2).lower())
    if not month:
        return None
    try:
        return date(int(m.group(3)), month, int(m.group(1)))
    except ValueError:
        return None


def temperatures(text: str) -> List[float]:
    return [float(v) for v in re.findall(rf"({NUM})\s*°?\s*C\b", text or "")]


AMBIENT = re.compile(r"\b(ambient|room temperature)\b", re.I)


def quantified_qualifiers(text: str) -> List[str]:
    """Quantified qualifiers inside an otherwise qualitative criterion, e.g.
    the '24 h' in 'No visible corrosion at 24 h'."""
    return [
        f"{m.group(1)} {m.group(2)}"
        for m in re.finditer(rf"\b({NUM})\s*(h|hr|hrs|hours|min|minutes|s|days?)\b", text or "", re.I)
    ]
