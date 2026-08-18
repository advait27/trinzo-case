"""Ingestion and table recovery."""

from __future__ import annotations

import unittest

from protocolqc import extract as ex
from protocolqc.ingest import load_pdf
from protocolqc.model import Document
from protocolqc.table import TableParseError, parse_table

from support import PROTOCOL_PDF, layout_text, load_docs, rebuild, replace_once


class TestIngest(unittest.TestCase):
    def setUp(self):
        self.protocol_doc, self.report_doc = load_docs()
        self.protocol = ex.parse_document(self.protocol_doc)
        self.report = ex.parse_document(self.report_doc)

    def test_extraction_is_deterministic(self):
        again = load_pdf(PROTOCOL_PDF, "protocol")
        self.assertEqual(self.protocol_doc.text_sha256, again.text_sha256)
        self.assertEqual(self.protocol_doc.file_sha256, again.file_sha256)

    def test_protocol_columns_recovered(self):
        self.assertEqual(
            self.protocol.table.field_names,
            ["test_id", "test_name", "criterion", "sample_size", "method"],
        )

    def test_report_column_alias_maps_to_sample_size(self):
        # The report heads the column "n tested", the protocol "Sample size".
        self.assertIn("sample_size", self.report.table.field_names)
        self.assertEqual(self.report.rows()["T1"].text("sample_size"), "25")

    def test_all_protocol_rows_found(self):
        self.assertEqual(self.protocol.test_ids(), ["T1", "T2", "T3", "T4", "T5"])
        self.assertEqual(self.report.test_ids(), ["T1", "T2", "T3", "T4"])

    def test_cells_are_column_bounded_not_line_bounded(self):
        # The failure mode of flattened extraction is bleeding the next column
        # into this one. T1's criterion must be the criterion and nothing else.
        self.assertEqual(self.protocol.rows()["T1"].text("criterion"), "≥ 5.0 N")
        self.assertEqual(self.protocol.rows()["T1"].text("sample_size"), "30")

    def test_wrapped_cell_is_rejoined_across_lines(self):
        # Wraps onto a second line in the source.
        self.assertEqual(
            self.protocol.rows()["T1"].text("method"),
            "Tensile pull to failure in 37°C saline bath; Instron 5943",
        )
        self.assertEqual(
            self.report.rows()["T2"].text("criterion"),
            "≤ 20 particles ≥10 µm per unit",
        )

    def test_mid_word_hyphen_wrap_is_rejoined_without_a_space(self):
        # "Per ISO 10993-" / "5" on two lines must not become "Per ISO 10993- 5".
        self.assertEqual(self.protocol.rows()["T5"].text("sample_size"), "Per ISO 10993-5")

    def test_header_metadata_parsed(self):
        self.assertEqual(ex.doc_id(self.protocol), "NV-200-TP-014")
        self.assertEqual(ex.version(self.protocol), "2.0")
        self.assertEqual(ex.protocol_reference(self.report)[:2], ("NV-200-TP-014", "1.0"))

    def test_sections_parsed(self):
        self.assertEqual(
            [s.title for s in self.report.sections], ["Summary", "Results", "Conclusion"]
        )

    def test_unrecognised_table_is_refused_not_guessed(self):
        text = replace_once(layout_text(self.protocol_doc), "Sample size", "Widgets XYZ")
        with self.assertRaises(TableParseError):
            parse_table(rebuild(self.protocol_doc, text))

    def test_missing_table_is_refused(self):
        doc = Document.from_text("protocol", "x", "1. Purpose\nNo table here at all.\n")
        with self.assertRaises(TableParseError):
            parse_table(doc)


if __name__ == "__main__":
    unittest.main()
