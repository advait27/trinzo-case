"""The AI path.

Every test here runs offline against a stub client. That is deliberate: a test
suite that needs a network call and an API key is a test suite nobody runs, and
the properties worth pinning are about *what the tool does with model output*,
not about the model.

The property under test throughout: a model can only ever cause the tool to
show text that is genuinely in the source document. Everything else it says is
discarded.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from protocolqc import extract as ex
from protocolqc.ai import client as client_mod
from protocolqc.ai.client import AIUnavailable, NvidiaClient, client_from_env, mask, resolve
from protocolqc.ai.extract import parse_with_ai, parse_document as ai_parse_document
from protocolqc.ai.locate import LocateStats, locate, locate_all, numbered
from protocolqc.ai.suggest import suggest
from protocolqc.model import Citation, Document, Finding
from protocolqc.rules import run_rules
from protocolqc.table import TableParseError
from protocolqc.verify import verify_citations

from support import layout_text, load_docs, rebuild, replace_once


class StubClient(NvidiaClient):
    """Returns canned replies. Records what it was asked, so a test can assert
    the model was never called on the deterministic path."""

    def __init__(self, reply: str):
        super().__init__(api_key="stub", model="stub/model")
        self.reply = reply
        self.prompts: list[str] = []

    def complete(self, system: str, user: str, *, json_object: bool = True) -> str:
        self.prompts.append(user)
        return self.reply


class TestLocateGate(unittest.TestCase):
    """locate() is the boundary. Nothing a model says gets past it unchecked."""

    @classmethod
    def setUpClass(cls):
        cls.protocol, cls.report = load_docs()

    def test_real_quote_yields_real_offsets(self):
        span = locate(self.protocol, "≥ 5.0 N", 20)
        self.assertIsNotNone(span)
        self.assertEqual(self.protocol.slice(span.page, span.line, span.start, span.end), span.text)

    def test_span_carries_the_documents_characters_not_the_models(self):
        # The model writes single spaces; the document has two.
        span = locate(self.protocol, "Version: 2.0", 5)
        self.assertEqual(span.text, "Version:  2.0")

    def test_invented_quote_is_refused(self):
        stats = LocateStats()
        self.assertIsNone(
            locate(self.protocol, "All tests met their acceptance criteria", 12, stats=stats))
        self.assertEqual(stats.not_found, 1)
        self.assertIn("does not occur", stats.discarded[0])

    def test_a_wrong_line_number_is_corrected_not_trusted(self):
        span = locate(self.protocol, "Tensile bond strength", 99)
        self.assertEqual(span.line, 20)

    def test_quote_split_across_lines_becomes_two_spans(self):
        spans = locate_all(
            self.protocol, "Tensile pull to failure in 37°C saline bath; Instron 5943", 20)
        self.assertEqual(len(spans), 2)
        for s in spans:
            self.assertEqual(self.protocol.slice(s.page, s.line, s.start, s.end), s.text)

    def test_numbered_view_does_not_alter_the_document(self):
        first = numbered(self.protocol).split("\n")[0]
        self.assertTrue(first.endswith(self.protocol.raw_line(1, 1)))


class TestAiExtraction(unittest.TestCase):
    """A document the parser refuses, recovered via the model."""

    @classmethod
    def setUpClass(cls):
        cls.protocol_doc, cls.report_doc = load_docs()
        # Break the header the deterministic table parser keys on.
        cls.odd = rebuild(
            cls.protocol_doc,
            replace_once(layout_text(cls.protocol_doc), "Test ID", "Ref no."),
        )

    def test_the_deterministic_parser_refuses_it(self):
        with self.assertRaises(TableParseError):
            ex.parse_document(self.odd)

    def test_without_a_client_it_still_refuses(self):
        with self.assertRaises(TableParseError):
            ai_parse_document(self.odd, None, is_report=False)

    def _reply_for(self, doc) -> str:
        rows = []
        for tid, name, crit, n in (("T1", "Tensile bond strength", "≥ 5.0 N", "30"),
                                   ("T2", "Coating particulate", "≤ 20 particles", "30")):
            line = next(i for i, l in enumerate(doc.pages[0], 1) if l.strip().startswith(tid + " "))
            rows.append({
                "test_id": {"value": tid, "line": line},
                "test_name": {"value": name, "line": line},
                "criterion": {"value": crit, "line": line},
                "sample_size": {"value": n, "line": line},
            })
        return json.dumps({
            "fields": [{"key": "version", "value": "2.0", "line": 5},
                       {"key": "document", "value": "NV-200-TP-014", "line": 3}],
            "sections": [{"number": 4, "title": "Reporting", "line": 29}],
            "tests": rows,
        })

    def test_model_located_structure_produces_a_usable_parsed_doc(self):
        client = StubClient(self._reply_for(self.odd))
        parsed, report = parse_with_ai(self.odd, client, is_report=False, reason="test")
        self.assertEqual(report.source, "ai-assisted")
        self.assertEqual(parsed.test_ids(), ["T1", "T2"])
        self.assertEqual(parsed.rows()["T1"].text("criterion"), "≥ 5.0 N")
        self.assertEqual(ex.version(parsed), "2.0")

    def test_every_cell_from_the_model_is_addressed_to_real_text(self):
        client = StubClient(self._reply_for(self.odd))
        parsed, _ = parse_with_ai(self.odd, client, is_report=False, reason="test")
        for row in parsed.table.rows:
            for name, cell in row.cells.items():
                for span in cell.spans:
                    with self.subTest(row=row.text("test_id"), cell=name):
                        self.assertEqual(
                            self.odd.slice(span.page, span.line, span.start, span.end), span.text)

    def test_invented_cells_are_dropped_not_shown(self):
        reply = json.loads(self._reply_for(self.odd))
        reply["tests"][0]["criterion"] = {"value": "≥ 99.0 N", "line": 20}   # not in the document
        reply["fields"].append({"key": "date", "value": "1 January 2099", "line": 6})
        client = StubClient(json.dumps(reply))
        parsed, report = parse_with_ai(self.odd, client, is_report=False, reason="test")

        self.assertEqual(parsed.rows()["T1"].text("criterion"), "")   # dropped entirely
        self.assertNotIn("Date", parsed.fields)
        self.assertEqual(len(report.discarded), 2)
        self.assertTrue(any("99.0" in d for d in report.discarded))

    def test_rules_run_on_ai_extraction_and_citations_verify(self):
        client = StubClient(self._reply_for(self.odd))
        parsed, _ = parse_with_ai(self.odd, client, is_report=False, reason="test")
        report = ex.parse_document(self.report_doc)
        findings, outcomes = run_rules(parsed, report)
        result = verify_citations(findings, {"protocol": self.odd, "report": self.report_doc})
        self.assertEqual(result.failures, [])
        self.assertTrue(findings)

    def test_deterministic_documents_never_reach_the_model(self):
        client = StubClient("{}")
        parsed, report = ai_parse_document(self.protocol_doc, client, is_report=False)
        self.assertEqual(report.source, "deterministic")
        self.assertEqual(client.prompts, [])


class TestSuggestions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.protocol_doc, cls.report_doc = load_docs()
        cls.protocol = ex.parse_document(cls.protocol_doc)
        cls.report = ex.parse_document(cls.report_doc)

    def _run(self, suggestions):
        client = StubClient(json.dumps({"suggestions": suggestions}))
        return suggest(self.protocol, self.report, client)

    def test_a_grounded_suggestion_survives_and_is_labelled(self):
        out, notes = self._run([{
            "scope": "T2",
            "observation": "The protocol names a particulate counting method the report does not restate.",
            "reviewer_action": "Confirm the counting method used.",
            "protocol_quote": "Particulate count per USP", "protocol_line": 20,
            "report_quote": "Max 12 particles", "report_line": 17,
        }])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].source, "ai-suggested")
        self.assertEqual(out[0].rule_id, "AI")
        self.assertEqual(out[0].id, "AI-001")
        self.assertEqual({c.doc for c in out[0].citations}, {"protocol", "report"})
        self.assertIn("may be wrong", out[0].uncertainty)

    def test_a_suggestion_with_invented_quotes_is_dropped(self):
        out, notes = self._run([{
            "scope": "T2", "observation": "Something differs here.",
            "protocol_quote": "the protocol requires perfection", "protocol_line": 20,
            "report_quote": "the report agrees entirely", "report_line": 17,
        }])
        self.assertEqual(out, [])
        self.assertTrue(any("no quote could be found" in n for n in notes))

    def test_verdict_language_is_rejected_rather_than_reworded(self):
        for phrase in ("This test fails the criterion.",
                       "The report is non-compliant with the protocol.",
                       "T2 passed as recorded."):
            with self.subTest(phrase):
                out, notes = self._run([{
                    "scope": "T2", "observation": phrase,
                    "protocol_quote": "Coating particulate", "protocol_line": 20,
                }])
                self.assertEqual(out, [])
                self.assertTrue(any("pass/fail language" in n for n in notes))

    def test_suggestions_are_capped(self):
        many = [{"scope": "document", "observation": f"Difference number {i}.",
                 "protocol_quote": "Coating particulate", "protocol_line": 20} for i in range(20)]
        out, _ = self._run(many)
        self.assertLessEqual(len(out), 6)

    def test_model_failure_does_not_break_the_review(self):
        class Broken(StubClient):
            def complete(self, system, user, *, json_object=True):
                raise AIUnavailable("network down")
        out, notes = suggest(self.protocol, self.report, Broken("{}"))
        self.assertEqual(out, [])
        self.assertTrue(any("unavailable" in n for n in notes))

    def test_malformed_json_is_reported_not_guessed(self):
        out, notes = suggest(self.protocol, self.report, StubClient("I think T1 looks fine."))
        self.assertEqual(out, [])
        self.assertTrue(notes)


class KeyEnvironment:
    """Runs a block with the key environment fully controlled: no inherited
    variables, and .env searched only inside a temporary directory.

    Without this, every test below would pass or fail depending on whether the
    machine running it happens to have a key configured -- which is exactly the
    kind of test that goes green in CI and red on the one laptop that matters.
    """

    NAMES = ("NVIDIA_API_KEY", "PROTOCOLQC_AI_MODEL", "NVIDIA_BASE_URL")

    def __init__(self, env_file_text=None, **environ):
        self.text = env_file_text
        self.environ = environ

    def __enter__(self):
        import os
        import tempfile
        self._saved = {n: os.environ.pop(n, None) for n in self.NAMES}
        for name, value in self.environ.items():
            os.environ[name] = value
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        if self.text is not None:
            (self.dir / ".env").write_text(self.text, encoding="utf-8")
        self._saved_dirs = client_mod._search_dirs
        client_mod._search_dirs = lambda: [self.dir]
        return self

    def __exit__(self, *exc):
        import os
        client_mod._search_dirs = self._saved_dirs
        self._tmp.cleanup()
        for name in self.NAMES:
            os.environ.pop(name, None)
        for name, value in self._saved.items():
            if value is not None:
                os.environ[name] = value
        return False


class TestHyphenWrappedQuotes(unittest.TestCase):
    """A PDF breaks a word across lines at a hyphen. table.py rejoins those when
    it builds a cell, so locate() has to recognise the same thing or the two
    disagree about whether a piece of text is in the document -- which is how a
    perfectly good citation gets thrown away.

    Observed live: a model quoted "Per ISO 10993-5" from the protocol's T5 row
    and the suggestion was dropped, because the document has "Per ISO 10993-" on
    one line and "5" in the same column on the next.
    """

    @classmethod
    def setUpClass(cls):
        cls.protocol, cls.report = load_docs()

    def _spans(self, quote, line_hint=26):
        return locate_all(self.protocol, quote, line_hint, 1, LocateStats(), "probe")

    def test_the_wrapped_cell_is_found(self):
        spans = self._spans("Per ISO 10993-5")
        self.assertEqual([s.text for s in spans], ["Per ISO 10993-", "5"])

    def test_the_spans_carry_the_documents_characters_not_the_models(self):
        # The quote asked for "10993-5"; what comes back is what is really
        # there, on two lines, which is the whole point of the indirection.
        for span in self._spans("Per ISO 10993-5"):
            self.assertEqual(span.text, self.protocol.slice(1, span.line, span.start, span.end))

    def test_a_fabricated_continuation_is_still_refused(self):
        # The head exists; the tail does not. Nothing may be located.
        self.assertEqual(self._spans("Per ISO 10993-9"), [])

    def test_a_continuation_in_the_wrong_column_is_refused(self):
        # "03" really does occur on the next line, inside "BC-NV200-03" -- but
        # in a different column, so it is not this cell's continuation. Without
        # the column test this would produce a citation pointing at the wrong
        # place, which is worse than producing none.
        self.assertEqual(self._spans("Per ISO 10993-03"), [])

    def test_ordinary_quotes_are_unaffected(self):
        spans = self._spans("Reactivity grade \u2264 2")
        self.assertEqual([s.text for s in spans], ["Reactivity grade \u2264 2"])

    def test_the_wrapped_citation_survives_the_citation_gate(self):
        """The gate re-checks every span independently. If it disagreed with
        locate() about a two-span citation, the whole run would abort with a
        CitationError -- so the two must be tested together, not just apart."""
        spans = self._spans("Per ISO 10993-5")
        finding = Finding(id="X-1", rule_id="R-00", rule_title="probe",
                          category="criteria", priority="low", scope="T5",
                          statement="s", basis="b", reviewer_action="a",
                          citations=[Citation("protocol", spans, "AI-located quote")])
        result = verify_citations([finding], {"protocol": self.protocol,
                                              "report": self.report})
        self.assertTrue(result.ok)
        self.assertEqual(result.spans_checked, 2)

    def test_the_quote_is_shown_on_two_lines_not_glued_together(self):
        # The document does not contain "Per ISO 10993-5" as continuous text,
        # so the reviewer must not be shown it as though it did.
        quote = Citation("protocol", self._spans("Per ISO 10993-5")).quote
        self.assertEqual(quote, "Per ISO 10993-\n5")

    def test_a_hyphenated_word_that_is_not_wrapped_still_matches_on_one_line(self):
        # The document reference is full of hyphens and sits entirely on one
        # line. The wrap handling must not fire and split it in two.
        spans = locate_all(self.report, "NV-200-VR-014", None, 1, LocateStats(), "probe")
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].text, "NV-200-VR-014")


class TestKeyResolution(unittest.TestCase):
    """Where the key comes from. This is ordinary configuration handling, but
    it is the one part of the AI path a user touches by hand, so the failure
    modes are worth pinning down."""

    def test_no_key_anywhere_names_both_places_to_put_one(self):
        with KeyEnvironment():
            with self.assertRaises(AIUnavailable) as ctx:
                client_from_env()
        message = str(ctx.exception)
        self.assertIn(".env", message)
        self.assertIn("NVIDIA_API_KEY", message)
        self.assertIn("deterministic checks", message)

    def test_a_key_in_a_dotenv_file_is_found(self):
        with KeyEnvironment("NVIDIA_API_KEY=nvapi-from-the-file-1234\n") as env:
            client = client_from_env()
            self.assertEqual(client.api_key, "nvapi-from-the-file-1234")
            self.assertEqual(client.key_origin, str(env.dir / ".env"))

    def test_the_environment_beats_the_file(self):
        # A checked-out file must never override what a runtime injected.
        with KeyEnvironment("NVIDIA_API_KEY=from-file\n", NVIDIA_API_KEY="from-env"):
            client = client_from_env()
            self.assertEqual(client.api_key, "from-env")
            self.assertIn("environment", client.key_origin)

    def test_file_syntax_people_actually_write(self):
        text = (
            "# a comment\n"
            "\n"
            '  export NVIDIA_API_KEY = "nvapi-quoted-and-exported"  \n'
            "PROTOCOLQC_AI_MODEL='some/model'\n"
            "NOT_A_LINE\n"
        )
        with KeyEnvironment(text):
            client = client_from_env()
            self.assertEqual(client.api_key, "nvapi-quoted-and-exported")
            self.assertEqual(client.model, "some/model")

    def test_an_explicit_model_argument_still_wins(self):
        with KeyEnvironment("NVIDIA_API_KEY=k\nPROTOCOLQC_AI_MODEL=from/file\n"):
            self.assertEqual(client_from_env("cli/model").model, "cli/model")

    def test_an_empty_value_is_not_a_key(self):
        with KeyEnvironment("NVIDIA_API_KEY=\n"):
            with self.assertRaises(AIUnavailable):
                client_from_env()

    def test_a_missing_variable_resolves_to_nothing_rather_than_raising(self):
        with KeyEnvironment("NVIDIA_API_KEY=k\n"):
            self.assertEqual(resolve("NVIDIA_BASE_URL"), ("", ""))


class TestKeyIsNeverPrinted(unittest.TestCase):
    """The tool prints which key it is using so a run is traceable. It must
    never print enough of one to be usable -- console output gets pasted into
    tickets and attached to records."""

    KEY = "nvapi-SECRETSECRETSECRETSECRET1234"

    def test_mask_hides_the_middle(self):
        masked = mask(self.KEY)
        self.assertNotIn("SECRET", masked)
        self.assertNotEqual(masked, self.KEY)
        self.assertTrue(masked.startswith("nvapi-"))
        self.assertTrue(masked.endswith("1234"))

    def test_a_short_key_reveals_nothing_at_all(self):
        self.assertEqual(mask("abc123"), "******")

    def test_describe_key_says_where_without_saying_what(self):
        described = NvidiaClient(api_key=self.KEY, key_origin="/tmp/.env").describe_key()
        self.assertNotIn("SECRET", described)
        self.assertIn("/tmp/.env", described)


class TestClient(unittest.TestCase):
    def test_temperature_is_zero_by_default(self):
        # Reproducibility matters more than variety for an extraction task.
        self.assertEqual(NvidiaClient(api_key="x").temperature, 0.0)


if __name__ == "__main__":
    unittest.main()
