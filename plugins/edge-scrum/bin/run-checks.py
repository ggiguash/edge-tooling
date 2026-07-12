#!/usr/bin/env python3
"""Run data-quality gate and 6 planning risk checks. Deterministic — no LLM needed."""

import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from _jira_transforms import load_json, write_output

DONE_STATUSES_STORIES = {"Closed"}
DONE_STATUSES_OCPBUGS = {"Closed", "Verified"}
DONE_STATUSES_EPICS = {"Closed", "Dev Complete"}

SIZE_TO_MAX_SPRINTS = {"XS": 2, "S": 3, "M": 4, "L": 4, "XL": 5}
DEFAULT_SP_TARGET = 8

COMPONENT_SHORT_NAMES = {
    "tna": "Two Node with Arbiter",
    "tnf": "Two Node Fencing",
    "lvms": "Logical Volume Manager Storage",
    "topolvm": "Logical Volume Manager Storage",
    "microshift": "MicroShift",
    "sno": "Installer / Single Node OpenShift",
}

def is_microshift_component(comp):
    """Match MicroShift and any subcomponent (MicroShift / Networking, etc.)."""
    return comp == "MicroShift" or comp.startswith("MicroShift / ")


# --- Hierarchy ---


def build_hierarchy(features, epics, stories, bugs, component_filter):
    """Build Feature -> Epics -> Stories tree. Returns list of enriched feature dicts."""
    epic_by_key = {e["key"]: e for e in epics.get("epics", [])}
    feature_to_epics = epics.get("feature_to_epics", {})

    stories_by_epic = {}
    for s in stories.get("stories", []):
        stories_by_epic.setdefault(s["epic_key"], []).append(s)

    cf_lower = component_filter.lower() if component_filter and component_filter != "none" else None
    cf_full = COMPONENT_SHORT_NAMES.get(cf_lower, cf_lower) if cf_lower else None
    is_microshift = cf_lower == "microshift" if cf_lower else False
    def matches_component(comp):
        if is_microshift:
            return is_microshift_component(comp)
        return comp == cf_full if cf_full else False

    result = []
    for f in features.get("features", []):
        fkey = f["key"]
        f_epics = []
        for ekey in feature_to_epics.get(fkey, []):
            epic = epic_by_key.get(ekey)
            if epic:
                epic_stories = stories_by_epic.get(ekey, [])
                f_epics.append({**epic, "stories": epic_stories})

        if cf_lower:
            has_match = False
            for e in f_epics:
                labels_lower = [lbl.lower() for lbl in e.get("labels", [])]
                if cf_lower in labels_lower:
                    has_match = True
                    break
                for s in e.get("stories", []):
                    s_comp = s.get("component", "")
                    if s_comp and matches_component(s_comp):
                        has_match = True
                        break
                    if is_microshift and s["key"].startswith("USHIFT-"):
                        has_match = True
                        break
                if has_match:
                    break
            if not has_match:
                continue

        all_stories = []
        for e in f_epics:
            all_stories.extend(e.get("stories", []))

        result.append({
            "key": fkey,
            "summary": f.get("summary", ""),
            "status": f.get("status", ""),
            "size": f.get("size", "Unsized"),
            "sme": f.get("sme", "None"),
            "type": f.get("type", "Feature"),
            "epics": f_epics,
            "all_stories": all_stories,
        })

    return result, bugs.get("bugs", [])


def is_story_done(story):
    if story["key"].startswith("OCPBUGS-"):
        return story["status"] in DONE_STATUSES_OCPBUGS
    return story["status"] in DONE_STATUSES_STORIES


# --- Data Quality Gate ---


def run_data_quality_gate(features):
    """Categorize each feature as PASS/WARN/FAIL."""
    results = []
    for f in features:
        epic_count = len(f["epics"])
        all_stories = f["all_stories"]
        non_bug_non_done = [s for s in all_stories if s["type"] != "Bug" and not is_story_done(s)]
        non_bug_all = [s for s in all_stories if s["type"] != "Bug"]
        story_count = len(non_bug_all)

        if epic_count == 0:
            status = "FAIL"
            reason = "no epics created"
        elif story_count == 0:
            status = "FAIL"
            reason = "epics have no stories"
        else:
            pointed = [s for s in non_bug_non_done if s["sp"] > 0]
            total_non_done = len(non_bug_non_done)
            pointed_pct = (len(pointed) / total_non_done * 100) if total_non_done > 0 else 100
            if pointed_pct >= 50:
                status = "PASS"
                reason = ""
            else:
                status = "WARN"
                reason = f"{100 - pointed_pct:.0f}% of stories lack story points"

        pointed_pct_val = 0
        if non_bug_non_done:
            pointed_pct_val = round(len([s for s in non_bug_non_done if s["sp"] > 0]) / len(non_bug_non_done) * 100)
        elif story_count > 0:
            pointed_pct_val = 100

        results.append({
            "feature_key": f["key"],
            "summary": f["summary"],
            "epic_count": epic_count,
            "story_count": story_count,
            "pointed_pct": pointed_pct_val,
            "status": status,
            "reason": reason,
        })

    return results


# --- Check 1: Capacity ---


def run_capacity_check(features, gate_results, roster, remaining_sprints):
    """Per-person capacity check. Only considers stories under PASS/WARN features."""
    passed_keys = {g["feature_key"] for g in gate_results if g["status"] in ("PASS", "WARN")}
    roster_map = {m["username"]: m for m in roster.get("members", [])}

    sp_by_person = {}
    person_features = {}
    person_display = {}

    for f in features:
        if f["key"] not in passed_keys:
            continue
        for s in f["all_stories"]:
            if is_story_done(s) or s["type"] == "Bug" or s["sp"] <= 0 or not s["assignee"]:
                continue
            sp_by_person[s["assignee"]] = sp_by_person.get(s["assignee"], 0) + s["sp"]
            person_features.setdefault(s["assignee"], set()).add(f["key"])
            person_display[s["assignee"]] = s.get("assignee_display", s["assignee"])

    results = []
    for person, assigned_sp in sorted(sp_by_person.items(), key=lambda x: -x[1]):
        member = roster_map.get(person, {})
        sp_target = member.get("sp_target", DEFAULT_SP_TARGET)
        capacity = sp_target * remaining_sprints
        overrun = max(0, assigned_sp - capacity)
        results.append({
            "person": person,
            "display_name": person_display.get(person, person),
            "assigned_sp": assigned_sp,
            "sp_target": sp_target,
            "remaining_capacity": capacity,
            "overrun": overrun,
            "status": "OVER" if overrun > 0 else "OK",
            "features": sorted(person_features.get(person, set())),
            "in_roster": person in roster_map,
        })

    return results


# --- Check 2: Timeline ---


def run_timeline_check(features, gate_results, roster, remaining_sprints):
    """Per-feature timeline projection with proportional velocity."""
    passed_keys = {g["feature_key"] for g in gate_results if g["status"] in ("PASS", "WARN")}
    roster_map = {m["username"]: m for m in roster.get("members", [])}

    global_sp = {}
    for f in features:
        for s in f["all_stories"]:
            if is_story_done(s) or s["type"] == "Bug" or s["sp"] <= 0 or not s["assignee"]:
                continue
            global_sp[s["assignee"]] = global_sp.get(s["assignee"], 0) + s["sp"]

    results = []
    for f in features:
        if f["key"] not in passed_keys:
            results.append({
                "feature_key": f["key"],
                "summary": f["summary"],
                "remaining_sp": 0,
                "velocity_per_sprint": 0,
                "sprints_needed": 0,
                "sprints_left": remaining_sprints,
                "gap": 0,
                "risk": "N/A",
            })
            continue

        remaining_sp = 0
        feature_sp_by_person = {}
        for s in f["all_stories"]:
            if not is_story_done(s):
                remaining_sp += s["sp"]
            if is_story_done(s) or s["type"] == "Bug" or s["sp"] <= 0 or not s["assignee"]:
                continue
            feature_sp_by_person[s["assignee"]] = feature_sp_by_person.get(s["assignee"], 0) + s["sp"]

        velocity = 0.0
        for person, person_feature_sp in feature_sp_by_person.items():
            sp_target = roster_map.get(person, {}).get("sp_target", DEFAULT_SP_TARGET)
            total_sp = global_sp.get(person, person_feature_sp)
            fraction = person_feature_sp / total_sp if total_sp > 0 else 0
            velocity += sp_target * fraction

        if velocity <= 0:
            sprints_needed = float("inf") if remaining_sp > 0 else 0
        else:
            sprints_needed = remaining_sp / velocity

        gap = max(0, sprints_needed - remaining_sprints) if sprints_needed != float("inf") else remaining_sprints
        risk = "NO_CONTRIBUTORS" if velocity <= 0 and remaining_sp > 0 else (
            "HIGH" if gap > 0 else "OK"
        )

        results.append({
            "feature_key": f["key"],
            "summary": f["summary"],
            "remaining_sp": remaining_sp,
            "velocity_per_sprint": round(velocity, 1),
            "sprints_needed": round(sprints_needed, 1) if sprints_needed != float("inf") else "inf",
            "sprints_left": remaining_sprints,
            "gap": round(gap, 1),
            "risk": risk,
        })

    return results


# --- Check 3: Assignment ---


def run_assignment_check(features):
    """SPOF detection and unassigned work. Non-bug stories only."""
    spof = []
    unassigned = []

    for f in features:
        non_done_non_bug = [s for s in f["all_stories"] if not is_story_done(s) and s["type"] != "Bug"]
        contributors = set(s["assignee"] for s in non_done_non_bug if s["assignee"])
        unassigned_stories = [s for s in non_done_non_bug if not s["assignee"]]

        if len(contributors) == 1:
            sole = list(contributors)[0]
            display = next(
                (s.get("assignee_display", sole) for s in non_done_non_bug if s["assignee"] == sole),
                sole
            )
            spof.append({
                "feature_key": f["key"],
                "summary": f["summary"],
                "sole_contributor": sole,
                "sole_contributor_display": display,
            })

        if unassigned_stories:
            unassigned_sp = sum(s["sp"] for s in unassigned_stories)
            unassigned.append({
                "feature_key": f["key"],
                "summary": f["summary"],
                "count": len(unassigned_stories),
                "sp": unassigned_sp,
            })

    return {"spof": spof, "unassigned": unassigned}


# --- Check 4: Bug Load ---


def run_bug_load_check(all_bugs, epic_stories, component_filter):
    """Unassigned Blocker/Critical bugs."""
    bugs = list(all_bugs)
    for s in epic_stories:
        if s["type"] == "Bug":
            bugs.append(s)

    cf_lower = component_filter.lower() if component_filter and component_filter != "none" else None
    is_ms = cf_lower == "microshift" if cf_lower else False
    cf_full = COMPONENT_SHORT_NAMES.get(cf_lower, cf_lower) if cf_lower else None

    if cf_lower:
        def bug_matches(comp):
            if is_ms:
                return is_microshift_component(comp)
            return comp == cf_full if cf_full else False
        bugs = [b for b in bugs if bug_matches(b.get("component", ""))]

    unassigned_bc = []
    by_component = {}

    for b in bugs:
        comp = b.get("component", "Unknown")
        priority = b.get("priority", "Major")
        by_component.setdefault(comp, {"total": 0, "blocker": 0, "critical": 0, "unassigned": 0})
        by_component[comp]["total"] += 1
        if priority == "Blocker":
            by_component[comp]["blocker"] += 1
        elif priority == "Critical":
            by_component[comp]["critical"] += 1

        if priority in ("Blocker", "Critical") and not b.get("assignee"):
            by_component[comp]["unassigned"] += 1
            unassigned_bc.append({
                "key": b["key"],
                "summary": b.get("summary", ""),
                "priority": priority,
                "component": comp,
                "status": b.get("status", ""),
            })

    return {
        "unassigned_blocker_critical": unassigned_bc,
        "by_component": by_component,
    }


# --- Check 5: Sizing ---


def run_sizing_check(features, timeline_results):
    """T-shirt size vs actual scope."""
    timeline_map = {t["feature_key"]: t for t in timeline_results}

    results = []
    for f in features:
        size = f["size"]
        total_sp = sum(s["sp"] for s in f["all_stories"] if not is_story_done(s))
        epic_count = len(f["epics"])
        contributors = set(
            s["assignee"] for s in f["all_stories"]
            if not is_story_done(s) and s["type"] != "Bug" and s["assignee"]
        )

        timeline = timeline_map.get(f["key"], {})
        sprints_needed = timeline.get("sprints_needed", 0)
        if sprints_needed == "inf":
            sprints_needed = 99

        assessment = "OK"
        if size == "Unsized":
            assessment = "Unsized"
        elif size in SIZE_TO_MAX_SPRINTS:
            max_sprints = SIZE_TO_MAX_SPRINTS[size]
            if isinstance(sprints_needed, (int, float)) and sprints_needed > max_sprints:
                assessment = "Undersized"
            elif size in ("XS", "S") and epic_count >= 4 and total_sp >= 50:
                assessment = "Undersized"
        else:
            assessment = "Unknown size"

        if assessment != "OK":
            results.append({
                "feature_key": f["key"],
                "summary": f["summary"],
                "tshirt": size,
                "actual_sp": total_sp,
                "epic_count": epic_count,
                "contributor_count": len(contributors),
                "sprints_needed": sprints_needed if sprints_needed != 99 else "N/A",
                "assessment": assessment,
            })

    return results


# --- Check 6: Composite ---


def run_composite_check(features, gate_results, capacity_results, timeline_results,
                         assignment_results, sizing_results):
    """Count signals per feature and assign composite risk."""
    gate_map = {g["feature_key"]: g["status"] for g in gate_results}
    overloaded_people = {c["person"] for c in capacity_results if c["status"] == "OVER"}
    timeline_risks = {t["feature_key"] for t in timeline_results if t["risk"] in ("HIGH", "NO_CONTRIBUTORS")}
    spof_keys = {s["feature_key"] for s in assignment_results["spof"]}
    unassigned_keys = {u["feature_key"] for u in assignment_results["unassigned"]}
    assignment_risk_keys = spof_keys | unassigned_keys
    sizing_keys = {s["feature_key"] for s in sizing_results}

    bug_keys_with_issues = set()
    for f in features:
        feature_bugs = [s for s in f["all_stories"] if s["type"] == "Bug"
                        and s.get("priority") in ("Blocker", "Critical") and not s.get("assignee")]
        if feature_bugs:
            bug_keys_with_issues.add(f["key"])

    results = []
    for f in features:
        fkey = f["key"]
        gate_status = gate_map.get(fkey, "PASS")
        signals = 0
        signal_details = {}

        if gate_status == "FAIL":
            signals += 1
            signal_details["data_quality"] = "FAIL"
        else:
            signal_details["data_quality"] = gate_status

        if fkey in timeline_risks:
            signals += 1
            signal_details["timeline"] = "HIGH"
        else:
            signal_details["timeline"] = "OK"

        feature_contributors = set(
            s["assignee"] for s in f["all_stories"]
            if not is_story_done(s) and s["type"] != "Bug" and s["assignee"]
        )
        if feature_contributors & overloaded_people:
            signals += 1
            signal_details["capacity"] = "HIGH"
        else:
            signal_details["capacity"] = "OK"

        if fkey in assignment_risk_keys:
            signals += 1
            has_spof = fkey in spof_keys
            has_unassigned = fkey in unassigned_keys
            if has_spof and has_unassigned:
                signal_details["assignment"] = "SPOF+Unassigned"
            elif has_spof:
                signal_details["assignment"] = "SPOF"
            else:
                signal_details["assignment"] = "Unassigned"
        else:
            signal_details["assignment"] = "OK"

        if fkey in bug_keys_with_issues:
            signals += 1
            signal_details["bugs"] = "HIGH"
        else:
            signal_details["bugs"] = "OK"

        if fkey in sizing_keys:
            signals += 1
            signal_details["sizing"] = "Mismatch"
        else:
            signal_details["sizing"] = "OK"

        if signals >= 3:
            composite_risk = "HIGH"
        elif signals == 2:
            composite_risk = "MEDIUM"
        else:
            composite_risk = "LOW"

        results.append({
            "feature_key": fkey,
            "summary": f["summary"],
            "signal_count": signals,
            "composite_risk": composite_risk,
            **signal_details,
        })

    results.sort(key=lambda x: ({"HIGH": 0, "MEDIUM": 1, "LOW": 2}.get(x["composite_risk"], 3), -x["signal_count"]))
    return results


# --- Main ---


def main():
    parser = argparse.ArgumentParser(description="Run planning risk checks")
    parser.add_argument("--features", required=True)
    parser.add_argument("--epics", required=True)
    parser.add_argument("--stories", required=True)
    parser.add_argument("--bugs", required=True)
    parser.add_argument("--roster", required=True)
    parser.add_argument("--remaining-sprints", type=int, required=True)
    parser.add_argument("--component-filter", default="none")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    features_data = load_json(args.features)
    epics_data = load_json(args.epics)
    stories_data = load_json(args.stories)
    bugs_data = load_json(args.bugs)
    roster = load_json(args.roster)

    if args.remaining_sprints == 0:
        print("WARNING: 0 sprints remaining — running post-branch-cut.", file=sys.stderr)

    features, unlinked_bugs = build_hierarchy(
        features_data, epics_data, stories_data, bugs_data, args.component_filter
    )

    all_epic_stories = []
    for f in features:
        all_epic_stories.extend(f["all_stories"])

    gate = run_data_quality_gate(features)
    capacity = run_capacity_check(features, gate, roster, args.remaining_sprints)
    timeline = run_timeline_check(features, gate, roster, args.remaining_sprints)
    assignment = run_assignment_check(features)
    bug_load = run_bug_load_check(unlinked_bugs, all_epic_stories, args.component_filter)
    sizing = run_sizing_check(features, timeline)
    composite = run_composite_check(features, gate, capacity, timeline, assignment, sizing)

    unknown_contributors = [c["person"] for c in capacity if not c["in_roster"]]

    stories_skipped = stories_data.get("skipped_issues", [])
    bugs_skipped = bugs_data.get("skipped_issues", [])

    high_count = sum(1 for c in composite if c["composite_risk"] == "HIGH")
    med_count = sum(1 for c in composite if c["composite_risk"] == "MEDIUM")
    low_count = sum(1 for c in composite if c["composite_risk"] == "LOW")
    assessed = sum(1 for g in gate if g["status"] in ("PASS", "WARN"))
    unassessable = sum(1 for g in gate if g["status"] == "FAIL")
    total_remaining = sum(t["remaining_sp"] for t in timeline if t["risk"] != "N/A")
    total_capacity = sum(c["remaining_capacity"] for c in capacity if c["in_roster"])

    overall = "HIGH" if high_count > 0 else ("MEDIUM" if med_count > 0 else "LOW")

    output = {
        "meta": {
            "total_features": len(features),
            "assessed_features": assessed,
            "unassessable_features": unassessable,
            "high_risk_count": high_count,
            "medium_risk_count": med_count,
            "low_risk_count": low_count,
            "overall_risk": overall,
            "total_remaining_sp": total_remaining,
            "total_capacity_sp": total_capacity,
            "overloaded_people_count": sum(1 for c in capacity if c["status"] == "OVER"),
            "spof_features_count": len(assignment["spof"]),
            "unassigned_blocker_bugs": len(bug_load["unassigned_blocker_critical"]),
            "data_quality_failures": unassessable,
            "component_filter": args.component_filter,
            "skipped_stories": len(stories_skipped),
            "skipped_bugs": len(bugs_skipped),
        },
        "data_quality": gate,
        "capacity": capacity,
        "timeline": timeline,
        "assignment": assignment,
        "bug_load": bug_load,
        "sizing": sizing,
        "composite": composite,
        "unknown_contributors": unknown_contributors,
        "skipped_issues": stories_skipped + bugs_skipped,
    }

    write_output(output, args.output)


if __name__ == "__main__":
    main()
