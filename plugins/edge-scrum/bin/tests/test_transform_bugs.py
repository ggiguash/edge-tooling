"""Tests for transform-bugs."""

import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from importlib import import_module

_mod = import_module("transform-bugs")
transform_bug = _mod.transform_bug
compute_aggregates = _mod.compute_aggregates
extract_component = _mod.extract_component

TODAY = "2026-07-09"


def _make_raw(key="OCPBUGS-1", summary="bug", status="NEW", priority="Major",
              assignee_email=None, component=None, labels=None, updated=None):
    raw = {
        "key": key,
        "summary": summary,
        "status": {"name": status},
        "priority": {"name": priority},
        "labels": labels or [],
        "updated": updated or TODAY,
        "created": TODAY,
    }
    if assignee_email:
        raw["assignee"] = {"email": assignee_email, "display_name": assignee_email.split("@")[0].title()}
    if component:
        raw["components"] = [{"name": component}]
    return raw


class TestExtractComponent(unittest.TestCase):
    def test_known_component(self):
        raw = {"components": [{"name": "Two Node Fencing"}]}
        assert extract_component(raw) == "Two Node Fencing"

    def test_unknown_component(self):
        raw = {"components": [{"name": "Networking"}]}
        assert extract_component(raw) == "Unknown"

    def test_no_components(self):
        assert extract_component({}) == "Unknown"

    def test_empty_components_list(self):
        raw = {"components": []}
        assert extract_component(raw) == "Unknown"

    def test_multiple_components_picks_team_one(self):
        raw = {"components": [{"name": "Networking"}, {"name": "Two Node with Arbiter"}]}
        assert extract_component(raw) == "Two Node with Arbiter"

    def test_none_components(self):
        raw = {"components": None}
        assert extract_component(raw) == "Unknown"


class TestTransformBug(unittest.TestCase):
    def test_basic_bug(self):
        raw = _make_raw(key="OCPBUGS-100", summary="crash", status="NEW",
                        priority="Blocker", component="Two Node Fencing")
        result = transform_bug(raw, TODAY)
        assert result["key"] == "OCPBUGS-100"
        assert result["priority"] == "Blocker"
        assert result["component"] == "Two Node Fencing"
        assert result["assignee"] is None
        assert result["assignee_display"] == "Unassigned"

    def test_assigned_bug(self):
        raw = _make_raw(assignee_email="alice@redhat.com")
        result = transform_bug(raw, TODAY)
        assert result["assignee"] == "alice@redhat.com"
        assert result["assignee_display"] == "Alice"

    def test_stale_bug(self):
        raw = _make_raw(updated="2026-06-01")
        result = transform_bug(raw, TODAY)
        assert result["stale"] is True

    def test_fresh_bug(self):
        raw = _make_raw(updated=TODAY)
        result = transform_bug(raw, TODAY)
        assert result["stale"] is False

    def test_labels_preserved(self):
        raw = _make_raw(labels=["cve", "regression"])
        result = transform_bug(raw, TODAY)
        assert result["labels"] == ["cve", "regression"]


class TestComputeAggregates(unittest.TestCase):
    def _bug(self, key="OCPBUGS-1", priority="Major", assignee=None,
             component="Two Node Fencing"):
        return {
            "key": key, "priority": priority, "assignee": assignee,
            "component": component,
        }

    def test_empty_list(self):
        agg = compute_aggregates([])
        assert agg["bugs_by_component"] == {}
        assert agg["bugs_by_priority"] == {}
        assert agg["unassigned_blocker_critical"] == []

    def test_bugs_by_component(self):
        bugs = [
            self._bug("B-1", component="Two Node Fencing"),
            self._bug("B-2", component="Two Node Fencing"),
            self._bug("B-3", component="Two Node with Arbiter"),
        ]
        agg = compute_aggregates(bugs)
        assert agg["bugs_by_component"]["Two Node Fencing"] == ["B-1", "B-2"]
        assert agg["bugs_by_component"]["Two Node with Arbiter"] == ["B-3"]

    def test_bugs_by_priority(self):
        bugs = [
            self._bug("B-1", priority="Blocker"),
            self._bug("B-2", priority="Critical"),
            self._bug("B-3", priority="Major"),
        ]
        agg = compute_aggregates(bugs)
        assert agg["bugs_by_priority"]["Blocker"] == ["B-1"]
        assert agg["bugs_by_priority"]["Critical"] == ["B-2"]
        assert agg["bugs_by_priority"]["Major"] == ["B-3"]

    def test_unassigned_blocker_critical(self):
        bugs = [
            self._bug("B-1", priority="Blocker", assignee=None),
            self._bug("B-2", priority="Critical", assignee=None),
            self._bug("B-3", priority="Major", assignee=None),
            self._bug("B-4", priority="Blocker", assignee="alice@redhat.com"),
        ]
        agg = compute_aggregates(bugs)
        assert agg["unassigned_blocker_critical"] == ["B-1", "B-2"]

    def test_assigned_blocker_not_flagged(self):
        bugs = [
            self._bug("B-1", priority="Blocker", assignee="alice@redhat.com"),
        ]
        agg = compute_aggregates(bugs)
        assert agg["unassigned_blocker_critical"] == []

    def test_unassigned_major_not_flagged(self):
        bugs = [
            self._bug("B-1", priority="Major", assignee=None),
        ]
        agg = compute_aggregates(bugs)
        assert agg["unassigned_blocker_critical"] == []


if __name__ == "__main__":
    unittest.main()
