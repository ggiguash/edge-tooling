# Edge Scrum Law: Epic and Feature Refinement

> The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in [RFC 2119](https://datatracker.ietf.org/doc/html/rfc2119).

## Epic Refinement Process

**Assignee** is responsible for getting an epic from Planning → To Do.

1. **Set baseline fields:** Component, Labels, QA Contact, Doc Contact, Size.
2. **Fill out epic description** using the standard template (goal, dependencies, completion criteria).
3. **Create stories:** Either directly (if implementation is clear) or via a refinement spike to allocate sprint capacity for investigation.
4. Move epic to **To Do** when steps 1–3 are complete.

**QA Contact:** If no QE is needed, MUST set to `unassigned_jira`. MUST NOT leave blank.  
**Doc Contact:** If no docs are needed, MUST set to `unassigned_jira`. MUST NOT leave blank.

## Feature / Initiative Refinement (SME Process)

The **SME** role is responsible for feature refinement. Assigned during release planning.

1. **Verify feature details:** Architect, SME, and Assignee are set; description has a clear goal.
2. **Create a refinement Spike** in OCPEDGE. Set component to match the feature. Spike MUST have a "blocks" relationship to the Feature/Initiative.
3. **Spike completion criteria:** All open questions answered, all dependencies identified, enough knowledge to write implementation stories.
4. **After spike:** Create deliverable Epics. Leave a comment on the Feature/Initiative indicating it's ready to move to "Backlog" state.

**Important:** Features SHOULD only contain epics that are **required** for the feature to complete. Optional or nice-to-have epics belong in an Initiative or as standalone epics.

## Implicit Refinement via Epics

A Feature with no child epics is considered **not refined** — there is no epic-level signal to assess. A Feature MAY be considered refined without a direct refinement spike when any of the following hold:

1. **Spike on epic**: A refinement spike in the refinement sprint blocks one of the Feature's child epics (rather than the Feature itself).
2. **Epics past Planning**: All child epics have moved past the **Planning** state, indicating that refinement happened at the epic level without a formal spike.
3. **Stories cover described work**: Each child epic's description outlines work to be done and the child stories/tasks already created under it appear to cover that described scope. This is an LLM-assessed judgment, not a mechanical check.

In all cases, agents SHOULD treat the Feature as refined (no spike-related risk). The preferred process is still to create a spike that blocks the Feature directly, but these alternatives are recognized as valid evidence of completed refinement.

**Exception:** If the Feature's own status is **New** or **Refinement**, these implicit signals do not apply. The Feature's workflow state is authoritative — a Feature explicitly in Refinement is not refined regardless of its epics' state.
