"""Repair of display quotes, licensed by a second extraction.

Layout-mode extraction reconstructs spacing from where glyphs sit on the page.
In justified paragraphs that occasionally opens a gap inside a word, so a
faithful quote can read "are con sidered to meet their criteria". A reviewer
seeing that reasonably stops trusting the quotes, which defeats the point.

The fix is evidence-based rather than cosmetic. pypdf's default extraction
reads the same PDF's character stream without using positions, and it renders
that word as "considered". Where the two independent extractions of the same
file disagree about a space inside a word, the word-preserving one is used for
display -- and only then. Nothing is merged unless the joined form actually
occurs, as a whole word, in the other extraction.

Two properties are deliberately preserved:
  * the raw span text is what gets stored in the JSON audit record and what
    the verification gate checks, so the evidence trail is untouched;
  * a merge can only ever remove a space, never add or change a character.
"""

from __future__ import annotations

import re
from typing import Dict, List

from .model import Citation, Document

TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9\-]*$")


class QuoteRepairer:
    def __init__(self, docs: Dict[str, Document]) -> None:
        self._flat = {
            key: [re.sub(r"\s+", " ", page) for page in (doc.flat_pages or [])]
            for key, doc in docs.items()
        }

    def _page(self, doc_key: str, page: int) -> str:
        pages = self._flat.get(doc_key) or []
        return pages[page - 1] if 0 < page <= len(pages) else ""

    @staticmethod
    def _whole_word(needle: str, haystack: str) -> bool:
        return bool(re.search(rf"(?<![A-Za-z0-9]){re.escape(needle)}(?![A-Za-z0-9])", haystack))

    def repair_line(self, doc_key: str, page: int, text: str) -> str:
        flat = self._page(doc_key, page)
        if not flat:
            return text
        parts: List[str] = text.split(" ")
        out: List[str] = []
        for part in parts:
            if out and TOKEN.match(out[-1]) and TOKEN.match(part):
                joined = out[-1] + part
                # Merge only if the other extraction shows this as one word AND
                # does not also show the two as separate words.
                if self._whole_word(joined, flat) and not self._whole_word(
                    f"{out[-1]} {part}", flat
                ):
                    out[-1] = joined
                    continue
            out.append(part)
        return " ".join(out)

    def quote(self, cite: Citation) -> str:
        page = cite.spans[0].page if cite.spans else 1
        return "\n".join(
            self.repair_line(cite.doc, page, line) for line in cite.quote.split("\n")
        )


class NullRepairer(QuoteRepairer):
    """Used when no second extraction is available, e.g. documents built from
    plain text in tests. Quotes pass through untouched."""

    def __init__(self) -> None:  # noqa: D107
        super().__init__({})

    def quote(self, cite: Citation) -> str:
        return cite.quote
