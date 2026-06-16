---
name: lvms:analyze
argument-hint: "[must-gather-path|--live] [--component storage|operator|volumes|logs]"
description: Analyze LVMS health — troubleshoot LVMCluster, volume groups, PVCs, and storage issues on live clusters or must-gather data
user-invocable: true
allowed-tools: Bash, Read, Glob, Grep
---

# lvms:analyze

## Synopsis

```bash
/lvms:analyze [must-gather-path] [--live] [--component <component>]
```

**Examples:**

```bash
# Full analysis on a live cluster
/lvms:analyze --live

# Analyze must-gather data offline
/lvms:analyze ./must-gather/registry-ci-openshift-org-origin-4-18.../

# Component-specific analysis
/lvms:analyze --live --component storage
/lvms:analyze ./must-gather/... --component logs
```

## Description

Diagnoses LVMS (Logical Volume Manager Storage) issues on OpenShift clusters. Operates in two modes:

- **Must-gather analysis**: Runs a Python script for structured offline analysis
- **Live cluster analysis**: Executes `oc` commands for real-time diagnostics

Detects: PVCs stuck Pending, LVMCluster not Ready, volume group creation failures, device conflicts, TopoLVM CSI issues, thin pool capacity problems, and operator/vg-manager pod errors.

## Prerequisites

**Live cluster:** `oc` CLI with active cluster connection and read access to the LVMS namespace.

**Must-gather:** Python 3 with PyYAML (`pip install pyyaml`). The must-gather path must point to the subdirectory containing `cluster-scoped-resources/` and `namespaces/` (not the parent).

**Namespace compatibility:** LVMS namespace changed from `openshift-storage` to `openshift-lvm-storage` in recent versions. Both are auto-detected.

## Implementation

### Step 1: Determine Mode

- `--live` flag present → live cluster analysis
- Path argument provided → must-gather analysis
- Neither → ask the user which mode to use

### Step 2: Determine Scope

Parse arguments for component focus:

| Keywords in args | Scope |
|---|---|
| `storage`, `pvc`, `pv`, `volumes`, `pending` | PVC/PV analysis only |
| `operator`, `lvmcluster`, `deployment`, `pods` | Operator health only |
| `vg`, `volume group`, `disk`, `device` | Volume group analysis only |
| `node`, `devices`, `lsblk` | Node device analysis (live only) |
| `logs`, `errors` | Pod log analysis only |
| No keywords or `all` | Full comprehensive analysis |

### Step 3: Must-Gather Analysis

Run the Python analysis script:

```bash
python3 plugins/lvms/skills/analyze/scripts/analyze_lvms.py <must-gather-path> [--component <component>]
```

Valid `--component` values: `all`, `storage`, `operator`, `volumes`, `vg`, `pvc`, `pods`, `logs`.

If the script is unavailable, fall back to reading must-gather files directly with the Read tool.

### Step 4: Live Cluster Analysis

First detect the LVMS namespace:

```bash
LVMS_NS=$(oc get namespace openshift-lvm-storage -o name 2>/dev/null | cut -d/ -f2)
if [ -z "$LVMS_NS" ]; then
    LVMS_NS="openshift-storage"
fi
```

Then collect and analyze resources depending on scope:

**LVMCluster health:**

```bash
oc get lvmcluster -n $LVMS_NS -o yaml
```

Check `status.state` (Ready/Progressing/Failed/Degraded), `status.ready`, and `status.conditions` (ResourcesAvailable, VolumeGroupsReady). Check `status.deviceClassStatuses` for per-node VG readiness.

**Volume groups:**

```bash
oc get lvmvolumegroup -A -o yaml
oc get lvmvolumegroupnodestatus -A -o yaml
```

Check VG creation per node, device availability, excluded devices and reasons. Common root causes for VG failures: device has existing filesystem (wipe with `wipefs -a`), duplicate VG names on the system conflicting with LVMS VG name, or device too small.

**PVC/PV status:**

```bash
oc get pvc -A -o json | jq '[.items[] | select(.spec.storageClassName | startswith("lvms-")) | select(.status.phase != "Bound")]'
oc get pv -o json | jq '[.items[] | select(.spec.csi.driver == "topolvm.io")]'
oc get storageclass -o json | jq '[.items[] | select(.provisioner == "topolvm.io")]'
```

For each pending PVC, check events: `oc get events -n <ns> --field-selector involvedObject.name=<pvc>`. Common causes: insufficient VG free space (thin pool full), VG missing on the node the PVC has affinity to, or node-specific device failure.

**Operator health:**

```bash
oc get pods -n $LVMS_NS -o wide
oc get deployment -n $LVMS_NS -o wide
oc get daemonset -n $LVMS_NS -o wide
```

Check for CrashLoopBackOff, high restart counts, missing replicas.

**Pod logs:**

```bash
oc logs -n $LVMS_NS deployment/lvms-operator --tail=500
for pod in $(oc get pods -n $LVMS_NS -l app.kubernetes.io/component=vg-manager -o name); do
    oc logs -n $LVMS_NS $pod --tail=500
done
```

Extract error/warning messages. Deduplicate repeated reconciliation errors.

**Node devices (live only):**

```bash
oc debug node/<node> -- chroot /host lsblk --paths --json -o NAME,ROTA,TYPE,SIZE,MODEL,FSTYPE,MOUNTPOINT
oc debug node/<node> -- chroot /host vgs -o vg_name,pv_name,vg_size,vg_free
```

### Step 5: Generate Report

Structure the output with these sections (include only relevant sections based on scope):

1. **LVMCluster Status** — state, readiness, conditions, device class node coverage
2. **Volume Group Status** — per-node VG state, devices, excluded devices with reasons
3. **Storage (PVC/PV) Status** — bound/pending counts, details for non-bound PVCs
4. **Operator Health** — deployment/daemonset replica counts, problematic pods
5. **Pod Logs Analysis** — unique error/warning messages grouped by pod
6. **Summary** — critical issues, warnings, root cause chain
7. **Recommendations** — prioritized remediation with specific `oc` commands and verification steps

Use visual indicators: `✓` (healthy), `⚠` (warning), `❌` (critical), `ℹ` (info).

Always end with actionable next steps including verification commands and a pointer to collect a fresh must-gather if needed:

```bash
oc adm must-gather --image=quay.io/lvms_dev/lvms-must-gather:latest
```
