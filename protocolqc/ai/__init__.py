"""Optional AI assistance, built on NVIDIA NIM.

Two capabilities, both strictly bounded:

  extract.py  -- when the deterministic parser does not recognise a document's
                 layout, a model proposes where the fields and table cells are.
                 It returns line numbers and quoted text; this package finds
                 that text in the document itself and builds the offsets.
                 Anything it cannot point at verbatim is discarded.

  suggest.py  -- advisory observations about differences the rule set does not
                 model (wording of a method, say). Same citation gate, kept in
                 a separate bucket, never mixed with rule findings.

What the model is never allowed to do: decide pass or fail, supply a character
offset, or have its text shown to a reviewer without that text being found in
the source document first.
"""

from .client import AIUnavailable, NvidiaClient, client_from_env

__all__ = ["AIUnavailable", "NvidiaClient", "client_from_env"]
