#!/usr/bin/env python3
"""Match spikes to features and produce spikes.json."""

import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from _jira_transforms import get_nested, load_json, load_issues, write_output


EPIC_PLANNING_STATE = "Planning"
FEATURE_PRE_REFINED_STATES = {"New", "Refinement"}


def epics_look_refined(epic_records):
    """Check if a set of epics collectively appear refined.

    True when every epic has moved past the Planning state, which per
    workflow-states law means "Refinement done; ready for sprint planning."
    """
    if not epic_records:
        return False
    return all(e.get("status") and e.get("status") != EPIC_PLANNING_STATE for e in epic_records)


def main():
    parser = argparse.ArgumentParser(
        description="Match spikes to features and produce spikes.json"
    )
    parser.add_argument(
        "--input", nargs="+", required=True,
        help="Raw MCP response file(s) for refinement sprint spikes",
    )
    parser.add_argument("--features-file", required=True, help="Path to features.json")
    parser.add_argument("--epics-file", required=True, help="Path to epics.json")
    parser.add_argument("--sprints-file", required=True, help="Path to sprints.json")
    parser.add_argument("--output", required=True, help="Output path")
    args = parser.parse_args()

    sprints_data = load_json(args.sprints_file)
    features_data = load_json(args.features_file)
    epics_data = load_json(args.epics_file)

    ref_sprint_closed = sprints_data.get("refinement_sprint_closed", False)
    features = features_data.get("features", [])
    feature_keys = set(features_data.get("feature_keys", []))

    feature_to_epics = epics_data.get("feature_to_epics", {})
    epics_by_key = {e["key"]: e for e in epics_data.get("epics", [])}

    # Load and normalize ref sprint spikes
    raw_spikes = load_issues(args.input)
    ref_spikes = []
    for raw in raw_spikes:
        ref_spikes.append(
            {
                "key": raw.get("key", ""),
                "summary": raw.get("summary", ""),
                "status": get_nested(raw, "status", "name") or "",
                "issuelinks": raw.get("issuelinks", []),
            }
        )

    # Build spike -> feature mapping from ref sprint spikes (outward "blocks" links)
    spike_to_features = {}
    for spike in ref_spikes:
        for link in spike.get("issuelinks", []):
            link_type = link.get("type", {})
            if link_type.get("outward") == "blocks":
                outward = link.get("outward_issue") or link.get("outwardIssue")
                if outward and outward.get("key") in feature_keys:
                    spike_to_features.setdefault(spike["key"], []).append(
                        outward["key"]
                    )

    # Index spike_candidates from features.json
    feature_spike_candidates = {}
    for feat in features:
        for sc in feat.get("spike_candidates", []):
            feature_spike_candidates.setdefault(feat["key"], []).append(sc)

    # Match spikes to each feature
    spike_map = {}
    for feat in features:
        fk = feat["key"]
        matched = set()

        # From ref sprint spikes that block this feature
        for spike in ref_spikes:
            if fk in spike_to_features.get(spike["key"], []):
                matched.add(spike["key"])

        # From spike_candidates already linked in features.json
        for sc in feature_spike_candidates.get(fk, []):
            matched.add(sc["key"])

        matched = sorted(matched)
        primary = matched[0] if matched else None

        # Determine primary spike status
        if primary:
            spike_obj = next((s for s in ref_spikes if s["key"] == primary), None)
            if spike_obj:
                spike_status = spike_obj["status"]
            else:
                sc_obj = next(
                    (
                        sc
                        for sc in feature_spike_candidates.get(fk, [])
                        if sc["key"] == primary
                    ),
                    None,
                )
                spike_status = sc_obj["status"] if sc_obj else "Unknown"
        else:
            spike_status = "Missing"

        spike_in_ref = primary is not None and any(
            s["key"] == primary for s in ref_spikes
        )

        # Detect spikes linked to child epics instead of the feature
        child_epic_keys = set(feature_to_epics.get(fk, []))
        on_epic_keys = []
        if primary is None and child_epic_keys:
            for spike in ref_spikes:
                for link in spike.get("issuelinks", []):
                    if link.get("type", {}).get("outward") == "blocks":
                        outward = link.get("outward_issue") or link.get("outwardIssue")
                        if outward and outward.get("key") in child_epic_keys:
                            on_epic_keys.append(outward["key"])

        # Check if child epics collectively appear refined.
        # If the feature itself is still in New/Refinement, its workflow state
        # is authoritative — don't override with epic-level signals.
        child_epics = [epics_by_key[ek] for ek in child_epic_keys if ek in epics_by_key]
        feat_status = feat.get("status", "")
        if feat_status in FEATURE_PRE_REFINED_STATES:
            appear_refined = False
        else:
            appear_refined = epics_look_refined(child_epics)

        spike_map[fk] = {
            "spike_key": primary,
            "spike_keys": matched,
            "spike_status": spike_status,
            "spike_in_ref_sprint": spike_in_ref,
            "spike_overdue": (
                ref_sprint_closed
                and primary is not None
                and spike_status != "Closed"
            ),
            "spike_missing": primary is None,
            "spike_on_epic": bool(on_epic_keys),
            "spike_on_epic_keys": sorted(set(on_epic_keys)),
            "feature_pre_refined": feat_status in FEATURE_PRE_REFINED_STATES,
            "epics_appear_refined": appear_refined,
        }

    # Summary
    total = len(features)
    with_spike = sum(1 for v in spike_map.values() if not v["spike_missing"])
    with_closed = sum(1 for v in spike_map.values() if v["spike_status"] == "Closed")
    missing = sum(1 for v in spike_map.values() if v["spike_missing"])
    on_epic = sum(1 for v in spike_map.values() if v["spike_on_epic"])
    refined_via_epics = sum(
        1 for v in spike_map.values()
        if v["spike_missing"]
        and not v["feature_pre_refined"]
        and (v["spike_on_epic"] or v["epics_appear_refined"])
    )

    output = {
        "spike_map": spike_map,
        "all_ref_sprint_spikes": ref_spikes,
        "summary": {
            "features_with_spike": with_spike,
            "features_with_closed_spike": with_closed,
            "features_missing_spike": missing,
            "features_spike_on_epic": on_epic,
            "features_refined_via_epics": refined_via_epics,
            "total_features": total,
        },
    }

    write_output(output, args.output)


if __name__ == "__main__":
    main()
