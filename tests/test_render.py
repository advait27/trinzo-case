"""The review sheet output.

The sheet is now a bundled React app inlined into one file. That buys a much
better interface and introduces two failure modes worth pinning: the page
could quietly start depending on the network, and document text could break
out of the embedded JSON block.
"""

from __future__ import annotations

import copy
import json
import re
import unittest

from protocolqc import extract as ex
from protocolqc.limits import unchecked
from protocolqc.quotes import QuoteRepairer
from protocolqc.render import manifest, to_html, to_json
from protocolqc.rules import RULESET_VERSION, run_rules
from protocolqc.verify import verify_citations

from support import load_docs


class TestReviewSheet(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.protocol_doc, cls.report_doc = load_docs()
        protocol = ex.parse_document(cls.protocol_doc)
        report = ex.parse_document(cls.report_doc)
        cls.findings, cls.outcomes = run_rules(protocol, report)
        docs = {"protocol": cls.protocol_doc, "report": cls.report_doc}
        cls.limits = unchecked(protocol, report)
        cls.repairer = QuoteRepairer(docs)
        cls.manifest = manifest(docs, verify_citations(cls.findings, docs), RULESET_VERSION)
        cls.names = {"protocol": cls.protocol_doc.name, "report": cls.report_doc.name}
        cls.html = to_html(cls.findings, cls.outcomes, cls.limits, cls.manifest,
                           cls.names, cls.repairer)

    def test_page_is_self_contained(self):
        """No CDN, no fonts, no fetch. The sheet has to open from a file://
        path on a machine with no network."""
        self.assertEqual(re.findall(r"<script[^>]+\bsrc=", self.html), [])
        self.assertEqual(re.findall(r"<link\b", self.html), [])
        self.assertNotIn("@import", self.html)
        self.assertEqual(re.findall(r"url\(\s*['\"]?https?:", self.html), [])
        self.assertEqual(re.findall(r"\bfetch\(|XMLHttpRequest", self.html), [])
        # The only absolute URLs allowed are XML namespaces and React's error
        # doc string -- neither is ever requested.
        for url in set(re.findall(r"https?://[\w./-]+", self.html)):
            with self.subTest(url):
                self.assertTrue(
                    url.startswith("http://www.w3.org/") or url.startswith("https://react.dev/"),
                    f"unexpected external URL in the review sheet: {url}",
                )

    def test_the_new_review_link_is_conditional(self):
        """The sheet is one self-contained file that gets opened from disk and
        emailed around. A link to the upload page is only correct when that page
        is reachable, so it must be guarded by a check on the served path -- an
        unconditional href="/" would be a dead link in every copy that is not
        being served by the app."""
        self.assertIn("/^\\/r\\/[0-9a-f]{12}", self.html,
                      "the served-path guard is missing from the bundle")

    def test_embedded_data_round_trips(self):
        block = re.search(
            r'<script type="application/json" id="review-data">(.*?)</script>',
            self.html, re.S,
        )
        self.assertIsNotNone(block)
        embedded = json.loads(block.group(1))
        direct = json.loads(to_json(self.findings, self.outcomes, self.limits,
                                    self.manifest, self.repairer))
        self.assertEqual(embedded, direct)
        self.assertEqual(len(embedded["findings"]), len(self.findings))

    def test_document_text_cannot_break_out_of_the_json_block(self):
        """A document containing '</script>' must not terminate the tag. The
        finding text is attacker-uncontrolled here but reviewer-supplied PDFs
        are not something this tool gets to assume anything about."""
        # Deep copy: Finding is mutable and shared across tests via setUpClass.
        hostile = copy.deepcopy(self.findings)
        hostile[0].statement = 'Reported </script><script>alert("x")</script> in the method column'
        html = to_html(hostile, self.outcomes, self.limits, self.manifest,
                       self.names, self.repairer)
        # Exactly two closing script tags: the data block and the bundle.
        self.assertEqual(html.count("</script>"), 2)
        block = re.search(
            r'<script type="application/json" id="review-data">(.*?)</script>',
            html, re.S,
        )
        payload = json.loads(block.group(1))
        self.assertIn("</script>", payload["findings"][0]["observation"])

    def test_noscript_fallback_states_the_boundary(self):
        fallback = re.search(r"<noscript>(.*?)</noscript>", self.html, re.S).group(1)
        self.assertIn("findings.json", fallback)
        self.assertIn("does not determine pass or fail", fallback)
        self.assertIn(str(len(self.findings)), fallback)

    def test_assets_are_present(self):
        from protocolqc.render import ASSETS
        for name in ("review-app.js", "review-app.css"):
            with self.subTest(name):
                self.assertTrue((ASSETS / name).exists(),
                                f"{name} missing -- run: cd ui && node build.mjs")

    def test_clean_run_still_renders(self):
        html = to_html([], self.outcomes, self.limits, self.manifest, self.names, self.repairer)
        self.assertIn('<div id="root"></div>', html)
        payload = json.loads(re.search(
            r'id="review-data">(.*?)</script>', html, re.S).group(1))
        self.assertEqual(payload["findings"], [])
        self.assertEqual(len(payload["rules_run"]), len(self.outcomes))


if __name__ == "__main__":
    unittest.main()
