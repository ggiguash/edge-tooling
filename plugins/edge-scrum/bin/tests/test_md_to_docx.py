"""Tests for md-to-docx parsing logic."""

import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from importlib import import_module

_mod = import_module("md-to-docx")
parse_md_lines = _mod.parse_md_lines
parse_table = _mod.parse_table
parse_inline = _mod.parse_inline
get_risk_level = _mod.get_risk_level


class TestParseMdLines(unittest.TestCase):
    def test_heading_levels(self):
        blocks = parse_md_lines("# Title\n## Section\n### Subsection")
        assert blocks[0] == ("h1", "Title")
        assert blocks[1] == ("h2", "Section")
        assert blocks[2] == ("h3", "Subsection")

    def test_paragraph(self):
        blocks = parse_md_lines("Some regular text here.")
        assert blocks[0] == ("paragraph", "Some regular text here.")

    def test_separator(self):
        blocks = parse_md_lines("---")
        assert blocks[0] == ("separator", "")

    def test_bullet_list(self):
        blocks = parse_md_lines("- Item one\n- Item two\n- Item three")
        assert blocks[0] == ("bullet_list", ["Item one", "Item two", "Item three"])

    def test_blockquote(self):
        blocks = parse_md_lines("> Quoted text here")
        assert blocks[0] == ("blockquote", "Quoted text here")

    def test_table_detected(self):
        md = "| A | B |\n|---|---|\n| 1 | 2 |"
        blocks = parse_md_lines(md)
        assert blocks[0][0] == "table"
        assert len(blocks[0][1]) == 3

    def test_empty_lines_skipped(self):
        blocks = parse_md_lines("\n\n\n")
        assert blocks == []

    def test_mixed_content(self):
        md = "# Title\n\nSome text.\n\n- Bullet\n\n---"
        blocks = parse_md_lines(md)
        types = [b[0] for b in blocks]
        assert types == ["h1", "paragraph", "bullet_list", "separator"]


class TestParseTable(unittest.TestCase):
    def test_basic_table(self):
        lines = ["| Name | Value |", "|---|---|", "| A | 1 |", "| B | 2 |"]
        header, rows = parse_table(lines)
        assert header == ["Name", "Value"]
        assert rows == [["A", "1"], ["B", "2"]]

    def test_empty_table(self):
        header, rows = parse_table([])
        assert header == []
        assert rows == []

    def test_header_only(self):
        lines = ["| Name | Value |", "|---|---|"]
        header, rows = parse_table(lines)
        assert header == ["Name", "Value"]
        assert rows == []

    def test_separator_row_filtered(self):
        lines = ["| A | B |", "|---|---|", "| 1 | 2 |"]
        header, rows = parse_table(lines)
        assert len(rows) == 1

    def test_whitespace_stripped(self):
        lines = ["| Name  |  Value |", "|---|---|", "|  A  |  1  |"]
        header, rows = parse_table(lines)
        assert header == ["Name", "Value"]
        assert rows == [["A", "1"]]


class TestParseInline(unittest.TestCase):
    def test_plain_text(self):
        segs = parse_inline("hello world")
        assert segs == [("text", "hello world")]

    def test_bold(self):
        segs = parse_inline("this is **bold** text")
        assert ("bold", "bold") in segs

    def test_italic(self):
        segs = parse_inline("this is *italic* text")
        assert ("italic", "italic") in segs

    def test_link(self):
        segs = parse_inline("see [OCPEDGE-123](https://example.com)")
        found = [s for s in segs if s[0] == "link"]
        assert len(found) == 1
        assert found[0][1] == "OCPEDGE-123"
        assert found[0][2] == "https://example.com"

    def test_mixed_formatting(self):
        segs = parse_inline("**bold** and *italic* and [link](url)")
        types = [s[0] for s in segs]
        assert "bold" in types
        assert "italic" in types
        assert "link" in types

    def test_no_formatting(self):
        segs = parse_inline("plain")
        assert segs == [("text", "plain")]


class TestGetRiskLevel(unittest.TestCase):
    def test_high(self):
        assert get_risk_level("HIGH") == "high"
        assert get_risk_level("high") == "high"

    def test_medium(self):
        assert get_risk_level("MEDIUM") == "medium"

    def test_low(self):
        assert get_risk_level("LOW") == "low"

    def test_pass(self):
        assert get_risk_level("PASS") == "low"

    def test_fail(self):
        assert get_risk_level("FAIL") == "high"

    def test_warn(self):
        assert get_risk_level("WARN") == "medium"

    def test_unknown(self):
        assert get_risk_level("something else") is None

    def test_with_whitespace(self):
        assert get_risk_level("  HIGH  ") == "high"

    def test_emoji_risk(self):
        assert get_risk_level("🔴") == "high"
        assert get_risk_level("🟡") == "medium"
        assert get_risk_level("🟢") == "low"


if __name__ == "__main__":
    unittest.main()
