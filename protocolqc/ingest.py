"""PDF -> Document.

Uses pypdf's layout extraction mode, which keeps the horizontal position of
text. That matters a lot here: in flattened extraction a table row becomes one
run-on sentence ("T1 Tensile bond strength >= 5.0 N 30 Tensile pull to ...")
and you have to guess where the acceptance criterion ends and the sample size
begins. In layout mode the columns stay in their original x positions and can
be recovered exactly, which is what makes reliable citations possible.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from pypdf import PdfReader

from .model import Document


def file_sha256(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_pdf(path: str | Path, key: str, name: str | None = None) -> Document:
    path = Path(path)
    reader = PdfReader(str(path))
    pages, flat = [], []
    for page in reader.pages:
        pages.append((page.extract_text(extraction_mode="layout") or "").split("\n"))
        # Second extraction, position-free. Only ever used to sanity-check the
        # spacing of a displayed quote (see quotes.py); never cited.
        flat.append(page.extract_text() or "")
    return Document(
        key=key,
        name=name or path.name,
        pages=pages,
        path=str(path),
        file_sha256=file_sha256(path),
        flat_pages=flat,
    )
