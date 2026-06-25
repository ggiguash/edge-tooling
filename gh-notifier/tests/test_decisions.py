"""Unit tests for edge-context decision parsing helpers in gh-notifier."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

_GH_NOTIFIER_PATH = Path(__file__).resolve().parent.parent / "gh-notifier.py"


def _load_gh_notifier():
    spec = importlib.util.spec_from_file_location("gh_notifier", _GH_NOTIFIER_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {_GH_NOTIFIER_PATH}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


gn = _load_gh_notifier()

_VALID_DECISION = """---
status: proposed
decision-makers: OpenShift Edge Team, PM
consulted:
---
# Integrate Chai Bot

## Context
"""


class TestDecisionFilenameRegex(unittest.TestCase):
    def test_matches_valid_decision_files(self):
        for name in (
            "0001-home-for-automated-slack-messages.md",
            "0123-slug.md",
            "9999-a.md",
        ):
            with self.subTest(name=name):
                self.assertIsNotNone(gn._DECISION_FILE_RE.match(name))

    def test_rejects_non_decision_files(self):
        for name in (
            "README.md",
            ".gitkeep",
            "00001-five-digit-prefix.md",
            "001-three-digit-prefix.md",
            "0002",
            "0002-.md",
            "0001-folder/notes.md",
        ):
            with self.subTest(name=name):
                self.assertIsNone(gn._DECISION_FILE_RE.match(name))


class TestParseFrontmatter(unittest.TestCase):
    def test_parses_valid_frontmatter(self):
        fm = gn.parse_frontmatter(_VALID_DECISION)
        self.assertEqual(fm["status"], "proposed")
        self.assertEqual(fm["decision-makers"], "OpenShift Edge Team, PM")

    def test_strips_quotes_from_values(self):
        text = '---\nstatus: "accepted"\ndecision-makers: "Alice, Bob"\n---\n'
        fm = gn.parse_frontmatter(text)
        self.assertEqual(fm["status"], "accepted")
        self.assertEqual(fm["decision-makers"], "Alice, Bob")

    def test_missing_opening_fence_returns_empty(self):
        self.assertEqual(gn.parse_frontmatter("status: proposed\n---\n"), {})

    def test_unclosed_frontmatter_returns_empty(self):
        self.assertEqual(gn.parse_frontmatter("---\nstatus: proposed\n"), {})

    def test_missing_status_key(self):
        text = "---\ndecision-makers: Alice\n---\n"
        fm = gn.parse_frontmatter(text)
        self.assertNotIn("status", fm)


class TestExtractDecisionTitle(unittest.TestCase):
    def test_extracts_title_after_frontmatter(self):
        self.assertEqual(gn.extract_decision_title(_VALID_DECISION), "Integrate Chai Bot")

    def test_no_heading_returns_empty(self):
        text = "---\nstatus: proposed\n---\n\nNo heading here.\n"
        self.assertEqual(gn.extract_decision_title(text), "")

    def test_finds_heading_without_frontmatter(self):
        self.assertEqual(gn.extract_decision_title("# Plain Title\n"), "Plain Title")


class TestDecisionNumberFromFilename(unittest.TestCase):
    def test_four_digit_prefix(self):
        self.assertEqual(
            gn.decision_number_from_filename("0002-integrate-chai-bot.md"),
            "0002",
        )

    def test_non_numeric_prefix_returns_full_name(self):
        self.assertEqual(gn.decision_number_from_filename("README.md"), "README.md")


class TestDecisionBlobUrl(unittest.TestCase):
    def test_encodes_ref_and_path(self):
        url = gn._decision_blob_url(
            "openshift-eng",
            "edge-context",
            "feature/branch",
            "decisions/0003-foo bar|unsafe>#1.md",
        )
        self.assertEqual(
            url,
            "https://github.com/openshift-eng/edge-context/blob/feature%2Fbranch/"
            "decisions/0003-foo%20bar%7Cunsafe%3E%231.md",
        )

    def test_main_branch_path(self):
        url = gn._decision_blob_url(
            gn._EDGE_CONTEXT_ORG,
            gn._EDGE_CONTEXT_REPO,
            gn._EDGE_CONTEXT_BRANCH,
            f"{gn._EDGE_CONTEXT_DECISIONS_PATH}/0002-slug.md",
        )
        self.assertEqual(
            url,
            "https://github.com/openshift-eng/edge-context/blob/main/decisions/0002-slug.md",
        )


class TestDecisionIncludedForDigest(unittest.TestCase):
    def test_includes_proposed_only(self):
        self.assertTrue(gn._decision_included_for_digest("proposed"))
        self.assertTrue(gn._decision_included_for_digest("PROPOSED"))
        for status in ("accepted", "rejected", "deprecated", "superseded", ""):
            with self.subTest(status=status):
                self.assertFalse(gn._decision_included_for_digest(status))


class TestIterMainDecisionFiles(unittest.TestCase):
    def test_yields_only_matching_filenames_on_main(self):
        listing = [
            {"type": "file", "name": "0001-slug.md"},
            {"type": "file", "name": "0002-another-slug.md"},
            {"type": "file", "name": "README.md"},
            {"type": "dir", "name": "templates"},
            {"type": "file", "name": ".gitkeep"},
            {"type": "file", "name": "001-bad-prefix.md"},
        ]

        def fake_gh_request(path, query=None):
            self.assertEqual(query, {"ref": "main"})
            return listing

        orig = gn.gh_request
        try:
            gn.gh_request = fake_gh_request
            names = list(gn.iter_main_decision_files())
        finally:
            gn.gh_request = orig

        self.assertEqual(names, ["0001-slug.md", "0002-another-slug.md"])


class TestIterOpenDecisionFiles(unittest.TestCase):
    def test_yields_decision_files_from_open_prs_to_main(self):
        def fake_gh_request(path, query=None):
            if path.endswith("/pulls"):
                self.assertEqual(query.get("base"), "main")
                self.assertEqual(query.get("state"), "open")
                return [{"number": 14, "head": {"sha": "abc123def456"}}]
            if path.endswith("/pulls/14/files"):
                self.assertEqual(query, {"per_page": "100", "page": "1"})
                return [
                    {
                        "filename": (
                            "decisions/0003-align-story-points-to-reward-"
                            "prioritizing-highest-priority-outcomes.md"
                        )
                    },
                    {"filename": "decisions/README.md"},
                    {"filename": "README.md"},
                ]
            raise AssertionError(f"unexpected path: {path} {query}")

        orig = gn.gh_request
        try:
            gn.gh_request = fake_gh_request
            sources = list(gn.iter_open_decision_files())
        finally:
            gn.gh_request = orig

        self.assertEqual(len(sources), 1)
        filename, head_sha, path = sources[0]
        self.assertEqual(filename, "0003-align-story-points-to-reward-prioritizing-highest-priority-outcomes.md")
        self.assertEqual(head_sha, "abc123def456")
        self.assertTrue(path.startswith("decisions/"))

    def test_rejects_nested_decision_paths_in_open_prs(self):
        def fake_gh_request(path, query=None):
            if path.endswith("/pulls"):
                return [{"number": 7, "head": {"sha": "deadbeef"}}]
            if path.endswith("/pulls/7/files"):
                return [
                    {"filename": "decisions/0001-valid-slug.md"},
                    {"filename": "decisions/0001-folder/notes.md"},
                ]
            raise AssertionError(f"unexpected path: {path}")

        orig = gn.gh_request
        try:
            gn.gh_request = fake_gh_request
            sources = list(gn.iter_open_decision_files())
        finally:
            gn.gh_request = orig

        self.assertEqual(len(sources), 1)
        filename, head_sha, repo_path = sources[0]
        self.assertEqual(filename, "0001-valid-slug.md")
        self.assertEqual(head_sha, "deadbeef")
        self.assertEqual(repo_path, "decisions/0001-valid-slug.md")

    def test_paginates_pr_files_endpoint(self):
        file_calls: list[dict[str, str] | None] = []

        def fake_gh_request(path, query=None):
            if path.endswith("/pulls"):
                return [{"number": 99, "head": {"sha": "sha1"}}]
            if path.endswith("/pulls/99/files"):
                file_calls.append(query)
                page = int((query or {}).get("page", 1))
                if page == 1:
                    return [{"filename": f"decisions/{i:04d}-decision.md"} for i in range(100)]
                if page == 2:
                    return [{"filename": "decisions/0100-extra-decision.md"}]
                return []
            raise AssertionError(f"unexpected path: {path}")

        orig = gn.gh_request
        try:
            gn.gh_request = fake_gh_request
            sources = list(gn.iter_open_decision_files())
        finally:
            gn.gh_request = orig

        self.assertEqual(len(sources), 101)
        self.assertEqual(file_calls[0], {"per_page": "100", "page": "1"})
        self.assertEqual(file_calls[1], {"per_page": "100", "page": "2"})


class TestPendingDecisionFromText(unittest.TestCase):
    def test_builds_pending_decision_for_proposed_status(self):
        decision = gn._pending_decision_from_text(
            _VALID_DECISION,
            "0002-integrate-chai-bot.md",
            "https://example.com/0002",
        )
        self.assertIsNotNone(decision)
        assert decision is not None
        self.assertEqual(decision.number, "0002")
        self.assertEqual(decision.title, "Integrate Chai Bot")
        self.assertEqual(decision.decision_makers, "OpenShift Edge Team, PM")

    def test_skips_non_matching_status(self):
        text = "---\nstatus: accepted\n---\n# Done\n"
        self.assertIsNone(
            gn._pending_decision_from_text(text, "0001-slug.md", "https://example.com")
        )


if __name__ == "__main__":
    unittest.main()
