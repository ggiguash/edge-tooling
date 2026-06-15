#!/usr/bin/env python3
"""
LVMS Must-Gather Analyzer

Analyzes LVMS must-gather data to identify and diagnose storage issues
including LVMCluster health, volume groups, PVC/PV problems, operator
issues, and TopoLVM CSI driver status.

Usage:
    python3 analyze_lvms.py <must-gather-path> [--component <component>]
"""

import os
import sys
import json
import argparse
from pathlib import Path
from collections import defaultdict

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML is required. Install with: pip install pyyaml", file=sys.stderr)
    sys.exit(1)


GREEN = '\033[92m'
YELLOW = '\033[93m'
RED = '\033[91m'
BLUE = '\033[94m'
BOLD = '\033[1m'
END = '\033[0m'


def section(title):
    sep = "=" * 79
    print(f"\n{sep}\n{BOLD}{title}{END}\n{sep}\n")


def ok(msg):
    print(f"{GREEN}✓{END} {msg}")


def warn(msg):
    print(f"{YELLOW}⚠{END}  {msg}")


def err(msg):
    print(f"{RED}❌{END} {msg}")


def info(msg):
    print(f"{BLUE}ℹ{END}  {msg}")


def load_yaml(path):
    try:
        with open(path, encoding='utf-8') as f:
            docs = list(yaml.safe_load_all(f))
            return docs[0] if len(docs) == 1 else docs
    except Exception as e:
        err(f"Failed to load {path}: {e}")
        return None


def extract_items(data):
    """Extract a flat list of resource items from parsed YAML data."""
    if data is None:
        return []
    if isinstance(data, list):
        return [d for d in data if d]
    if isinstance(data, dict):
        if data.get('items'):
            return data['items']
        if data.get('kind'):
            return [data]
    return []


class LVMSAnalyzer:
    NAMESPACES = ["openshift-lvm-storage", "openshift-storage"]

    def __init__(self, base_path):
        self.base = Path(base_path)
        self.ns = None
        self.lvmclusters = []
        self.pods = []
        self.events = []
        self.pvcs = []
        self.pvs = []
        self.storage_classes = []
        self.deployments = []
        self.daemonsets = []
        self.pod_logs = []
        self.issues = {'critical': [], 'warning': [], 'info': []}

    def validate(self):
        for ns in self.NAMESPACES:
            if (self.base / "namespaces" / ns).exists():
                self.ns = ns
                if ns == "openshift-storage":
                    info(f"Detected older LVMS namespace: {ns}")
                else:
                    info(f"Detected LVMS namespace: {ns}")
                return True

        err(f"LVMS namespace not found in: {self.base}")
        for ns in self.NAMESPACES:
            hits = list(self.base.glob(f"*/namespaces/{ns}"))
            if hits:
                info(f"Found '{ns}' at: {hits[0].parent.parent}")
                info("Use that subdirectory as the must-gather path")
                return False
        err("No openshift-lvm-storage or openshift-storage namespace found")
        return False

    def load_resources(self):
        info("Loading LVMS resources...")
        ns_dir = self.base / "namespaces" / self.ns
        oc_out = ns_dir / "oc_output"

        # LVMCluster — try oc_output (LVMS must-gather), then API group dirs (general must-gather)
        lc_file = oc_out / "lvmcluster.yaml"
        if lc_file.exists():
            self.lvmclusters = extract_items(load_yaml(lc_file))
        else:
            for f in ns_dir.rglob("lvmclusters.yaml"):
                self.lvmclusters.extend(extract_items(load_yaml(f)))
            if not self.lvmclusters:
                for f in ns_dir.rglob("lvmclusters/*.yaml"):
                    self.lvmclusters.extend(extract_items(load_yaml(f)))

        # Pods
        pods_dir = ns_dir / "pods"
        if pods_dir.exists():
            for pod_dir in pods_dir.iterdir():
                if pod_dir.is_dir():
                    pod_yaml = pod_dir / f"{pod_dir.name}.yaml"
                    if pod_yaml.exists():
                        data = load_yaml(pod_yaml)
                        if isinstance(data, dict) and data.get('kind') == 'Pod':
                            self.pods.append(data)

        # Events
        for f in (ns_dir / "core").rglob("events.yaml") if (ns_dir / "core").exists() else []:
            self.events.extend(extract_items(load_yaml(f)))

        # PVCs (all namespaces, filter for LVMS)
        for f in (self.base / "namespaces").rglob("persistentvolumeclaims.yaml"):
            for pvc in extract_items(load_yaml(f)):
                sc = pvc.get('spec', {}).get('storageClassName', '')
                if sc.startswith('lvms-') or sc.startswith('topolvm-'):
                    self.pvcs.append(pvc)

        # PVs — handle both individual files and list files, dedup by UID
        seen_pv_uids = set()
        pv_dir = self.base / "cluster-scoped-resources" / "core" / "persistentvolumes"
        if pv_dir.exists() and pv_dir.is_dir():
            for f in pv_dir.glob("*.yaml"):
                for pv in extract_items(load_yaml(f)):
                    uid = pv.get('metadata', {}).get('uid', '')
                    if pv.get('spec', {}).get('csi', {}).get('driver') == 'topolvm.io' and uid not in seen_pv_uids:
                        seen_pv_uids.add(uid)
                        self.pvs.append(pv)
        for f in (self.base / "cluster-scoped-resources" / "core").rglob("persistentvolumes.yaml"):
            for pv in extract_items(load_yaml(f)):
                uid = pv.get('metadata', {}).get('uid', '')
                if pv.get('spec', {}).get('csi', {}).get('driver') == 'topolvm.io' and uid not in seen_pv_uids:
                    seen_pv_uids.add(uid)
                    self.pvs.append(pv)

        # Storage classes — handle both individual files and list files, dedup by name
        seen_sc_names = set()
        sc_dir = self.base / "cluster-scoped-resources" / "storage.k8s.io" / "storageclasses"
        if sc_dir.exists() and sc_dir.is_dir():
            for f in sc_dir.glob("*.yaml"):
                for sc in extract_items(load_yaml(f)):
                    name = sc.get('metadata', {}).get('name', '')
                    if sc.get('provisioner') == 'topolvm.io' and name not in seen_sc_names:
                        seen_sc_names.add(name)
                        self.storage_classes.append(sc)
        for f in (self.base / "cluster-scoped-resources" / "storage.k8s.io").rglob("storageclasses.yaml"):
            for sc in extract_items(load_yaml(f)):
                name = sc.get('metadata', {}).get('name', '')
                if sc.get('provisioner') == 'topolvm.io' and name not in seen_sc_names:
                    seen_sc_names.add(name)
                    self.storage_classes.append(sc)

        # Deployments and DaemonSets
        apps_dir = ns_dir / "apps"
        if apps_dir.exists():
            for f in apps_dir.rglob("deployments.yaml"):
                self.deployments.extend(extract_items(load_yaml(f)))
            for f in apps_dir.rglob("daemonsets.yaml"):
                self.daemonsets.extend(extract_items(load_yaml(f)))

        ok(f"Loaded {len(self.lvmclusters)} LVMCluster(s), {len(self.pods)} pod(s), "
           f"{len(self.pvcs)} LVMS PVC(s), {len(self.pvs)} LVMS PV(s)")

    def load_pod_logs(self):
        info("Loading pod logs...")
        pods_dir = self.base / "namespaces" / self.ns / "pods"
        if not pods_dir.exists():
            return

        raw_entries = []
        for pod_dir in pods_dir.iterdir():
            if not pod_dir.is_dir():
                continue
            for container_dir in pod_dir.iterdir():
                if not container_dir.is_dir():
                    continue
                log_file = container_dir / container_dir.name / "logs" / "current.log"
                if log_file.exists():
                    raw_entries.extend(self._parse_log(log_file, pod_dir.name))

        # Deduplicate by message, keep earliest
        seen = {}
        for e in raw_entries:
            key = (e['pod'], e['msg'])
            if key not in seen or e['ts'] < seen[key]['ts']:
                seen[key] = e
        self.pod_logs = list(seen.values())
        ok(f"Found {len(self.pod_logs)} unique error/warning log entries")

    def _parse_log(self, path, pod_name):
        entries = []
        try:
            with open(path, encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    parts = line.split(' ', 1)
                    if len(parts) < 2:
                        continue
                    try:
                        entry = json.loads(parts[1])
                    except (json.JSONDecodeError, IndexError):
                        continue
                    level = entry.get('level', '').lower()
                    if level in ('error', 'warning'):
                        entries.append({
                            'pod': pod_name,
                            'level': level,
                            'ts': entry.get('ts', ''),
                            'msg': entry.get('msg', ''),
                            'error': entry.get('error', ''),
                            'controller': entry.get('controller', ''),
                        })
        except Exception as e:
            err(f"Failed to parse {path}: {e}")
        return entries

    def analyze_lvmcluster(self):
        section("LVMCLUSTER STATUS")
        if not self.lvmclusters:
            has_lvms_components = bool(self.pods or self.deployments or self.daemonsets)
            if has_lvms_components:
                warn("No LVMCluster resources found (general OCP must-gather does not capture CRDs)")
                info("Use LVMS-specific must-gather for full analysis:")
                info("  oc adm must-gather --image=quay.io/lvms_dev/lvms-must-gather:latest")
                self.issues['warning'].append("LVMCluster data not available (use LVMS must-gather for CRD data)")
            else:
                warn("No LVMCluster resources found")
                self.issues['critical'].append("No LVMCluster configured")
            return

        for cluster in self.lvmclusters:
            name = cluster.get('metadata', {}).get('name', 'unknown')
            status = cluster.get('status', {})
            state = status.get('state', 'Unknown')
            ready = status.get('ready', False)

            print(f"\n{BOLD}LVMCluster:{END} {name}")
            if state == 'Ready' and ready:
                ok(f"State: {state}")
                ok(f"Ready: {ready}")
            elif state == 'Progressing':
                warn(f"State: {state}")
                self.issues['warning'].append(f"LVMCluster {name}: Progressing")
            else:
                err(f"State: {state}")
                err(f"Ready: {ready}")
                self.issues['critical'].append(f"LVMCluster {name} not Ready (state: {state})")

            for cond in status.get('conditions', []):
                ctype = cond.get('type', '')
                cstatus = cond.get('status', '')
                reason = cond.get('reason', '')
                message = cond.get('message', '')
                if cstatus == 'True':
                    ok(f"{ctype}: {cstatus}")
                else:
                    err(f"{ctype}: {cstatus}")
                    if reason:
                        print(f"  Reason: {reason}")
                    if message:
                        print(f"  Message: {message}")
                    self.issues['critical'].append(f"{ctype}: {message or reason}")

            for dc in status.get('deviceClassStatuses', []):
                dc_name = dc.get('name', 'unknown')
                nodes = dc.get('nodeStatus', [])
                ready_count = sum(1 for n in nodes if n.get('status') == 'Ready')
                total = len(nodes)

                print(f"\n  {BOLD}Device Class:{END} {dc_name}")
                if ready_count == total and total > 0:
                    ok(f"  Nodes: {ready_count}/{total} Ready")
                elif ready_count > 0:
                    warn(f"  Nodes: {ready_count}/{total} Ready")
                    self.issues['warning'].append(f"Device class {dc_name}: {ready_count}/{total} nodes ready")
                else:
                    err(f"  Nodes: {ready_count}/{total} Ready")
                    self.issues['critical'].append(f"Device class {dc_name}: no nodes ready")

                failed = [n.get('node', '?') for n in nodes if n.get('status') != 'Ready']
                if failed:
                    print(f"  Not ready: {', '.join(failed)}")

    def analyze_volume_groups(self):
        section("VOLUME GROUP STATUS")
        if not self.lvmclusters:
            warn("No LVMCluster resources to extract VG info from")
            return

        for cluster in self.lvmclusters:
            for dc in cluster.get('status', {}).get('deviceClassStatuses', []):
                vg_name = dc.get('name', 'unknown')
                nodes = dc.get('nodeStatus', [])
                print(f"\n{BOLD}Volume Group/Device Class:{END} {vg_name}")
                print(f"Nodes: {len(nodes)}")

                for ns in nodes:
                    node = ns.get('node', 'unknown')
                    st = ns.get('status', 'Unknown')
                    reason = ns.get('reason', '')
                    devices = ns.get('devices', [])
                    excluded = ns.get('excluded', [])

                    print(f"\n  {BOLD}Node:{END} {node}")
                    if st == 'Ready':
                        ok(f"  Status: {st}")
                    elif st == 'Progressing':
                        warn(f"  Status: {st}")
                        self.issues['warning'].append(f"VG {vg_name} on {node}: Progressing")
                    else:
                        err(f"  Status: {st}")
                        self.issues['critical'].append(f"VG {vg_name} on {node}: {st}")

                    if reason and st != 'Ready':
                        print(f"\n  {BOLD}Reason:{END}")
                        lines = reason.split('\n')
                        for line in lines[:5]:
                            print(f"  {line}")
                        if len(lines) > 5:
                            print(f"  ... (truncated, {len(lines) - 5} more lines)")
                        if st != 'Progressing':
                            self.issues['critical'].append(f"VG {vg_name} on {node}: {reason[:200]}")

                    valid = [d for d in devices if d != '[unknown]']
                    if valid:
                        print(f"\n  Devices: {', '.join(valid)}")
                    elif devices:
                        warn("  Devices: none valid")

                    if excluded:
                        print(f"\n  Excluded devices: {len(excluded)}")
                        for ex in excluded[:3]:
                            name = ex.get('name', '?')
                            reasons = ex.get('reasons', [])
                            print(f"    - {name}: {reasons[0] if reasons else 'unknown reason'}")
                        if len(excluded) > 3:
                            print(f"    ... and {len(excluded) - 3} more")

    def analyze_pvcs(self):
        section("STORAGE (PVC/PV) STATUS")
        if not self.pvcs:
            info("No PVCs using LVMS storage classes found")
            return

        counts = defaultdict(int)
        pending = []
        for pvc in self.pvcs:
            phase = pvc.get('status', {}).get('phase', 'Unknown')
            counts[phase] += 1
            if phase != 'Bound':
                pending.append(pvc)

        print(f"Total LVMS PVCs: {len(self.pvcs)}")
        for phase, count in sorted(counts.items()):
            (ok if phase == 'Bound' else err)(f"{phase}: {count}")

        if pending:
            print(f"\n{BOLD}Non-Bound PVCs:{END}\n")
            for pvc in pending:
                ns = pvc.get('metadata', {}).get('namespace', '?')
                name = pvc.get('metadata', {}).get('name', '?')
                phase = pvc.get('status', {}).get('phase', '?')
                sc = pvc.get('spec', {}).get('storageClassName', '?')
                size = pvc.get('spec', {}).get('resources', {}).get('requests', {}).get('storage', '?')

                print(f"{BOLD}{ns}/{name}{END}")
                err(f"  Status: {phase}")
                print(f"  Storage Class: {sc}")
                print(f"  Requested: {size}")

                related = [e for e in self.events
                           if e.get('involvedObject', {}).get('name') == name
                           and e.get('involvedObject', {}).get('namespace') == ns]
                for event in related[-3:]:
                    etype = event.get('type', 'Normal')
                    r = event.get('reason', '')
                    m = event.get('message', '')
                    (warn if etype == 'Warning' else info)(f"  {r}: {m}")

                self.issues['critical'].append(f"PVC {ns}/{name}: {phase}")
                print()

    def analyze_operator_health(self):
        section("OPERATOR HEALTH")

        if self.deployments:
            print(f"{BOLD}Deployments:{END}\n")
            for d in self.deployments:
                name = d.get('metadata', {}).get('name', '?')
                desired = d.get('spec', {}).get('replicas', 0)
                ready = d.get('status', {}).get('readyReplicas', 0)
                if ready == desired and desired > 0:
                    ok(f"{name}: {ready}/{desired} replicas ready")
                else:
                    err(f"{name}: {ready}/{desired} replicas ready")
                    self.issues['critical'].append(f"Deployment {name}: {ready}/{desired} ready")

        if self.daemonsets:
            print(f"\n{BOLD}DaemonSets:{END}\n")
            for ds in self.daemonsets:
                name = ds.get('metadata', {}).get('name', '?')
                desired = ds.get('status', {}).get('desiredNumberScheduled', 0)
                ready = ds.get('status', {}).get('numberReady', 0)
                if ready == desired and desired > 0:
                    ok(f"{name}: {ready}/{desired} nodes ready")
                else:
                    warn(f"{name}: {ready}/{desired} nodes ready")
                    self.issues['warning'].append(f"DaemonSet {name}: {ready}/{desired} ready")

        bad_pods = [p for p in self.pods
                    if p.get('status', {}).get('phase') not in ('Running', 'Succeeded')]
        if bad_pods:
            print(f"\n{BOLD}Problematic Pods:{END}\n")
            for pod in bad_pods:
                name = pod.get('metadata', {}).get('name', '?')
                phase = pod.get('status', {}).get('phase', '?')
                err(f"{name}: {phase}")
                for cs in pod.get('status', {}).get('containerStatuses', []):
                    restarts = cs.get('restartCount', 0)
                    if restarts > 0:
                        print(f"  {cs.get('name', '?')}: {restarts} restarts")
                    waiting = cs.get('state', {}).get('waiting', {})
                    if waiting:
                        warn(f"  Waiting: {waiting.get('reason', '')}")
                    terminated = cs.get('state', {}).get('terminated', {})
                    if terminated:
                        err(f"  Terminated: {terminated.get('reason', '')} (exit {terminated.get('exitCode', '?')})")
                self.issues['critical'].append(f"Pod {name}: {phase}")
                print()

    def analyze_storage_classes(self):
        section("TOPOLVM STORAGE CLASSES")
        if not self.storage_classes:
            warn("No TopoLVM storage classes found")
            self.issues['warning'].append("No TopoLVM storage classes configured")
            return

        for sc in self.storage_classes:
            name = sc.get('metadata', {}).get('name', '?')
            ok(name)
            print(f"  Provisioner: {sc.get('provisioner', '?')}")
            print(f"  Binding Mode: {sc.get('volumeBindingMode', 'Immediate')}")
            params = sc.get('parameters', {})
            if params:
                for k, v in params.items():
                    print(f"  {k}: {v}")
            print()

    def analyze_pod_logs(self):
        section("POD LOGS ANALYSIS")
        if not self.pod_logs:
            info("No error or warning messages found in pod logs")
            return

        by_pod = defaultdict(list)
        for entry in self.pod_logs:
            by_pod[entry['pod']].append(entry)

        for pod, entries in sorted(by_pod.items()):
            print(f"\n{BOLD}Pod:{END} {pod}")
            print(f"Unique errors/warnings: {len(entries)}\n")
            for e in sorted(entries, key=lambda x: x['ts']):
                (err if e['level'] == 'error' else warn)(f"{e['ts']}: {e['msg']}")
                if e['controller']:
                    print(f"  Controller: {e['controller']}")
                if e['error']:
                    lines = e['error'].split('\n')
                    if len(lines) > 1:
                        print(f"  {BOLD}Error Details:{END}")
                        for line in lines[:10]:
                            if line.strip():
                                print(f"    {line}")
                        if len(lines) > 10:
                            print(f"    ... ({len(lines) - 10} more lines)")
                    else:
                        print(f"  Error: {e['error']}")
                if e['level'] == 'error':
                    self.issues['critical'].append(f"Pod {pod}: {e['msg']}")
                else:
                    self.issues['warning'].append(f"Pod {pod}: {e['msg']}")
                print()

    def summary(self):
        section("LVMS ANALYSIS SUMMARY")
        c = len(self.issues['critical'])
        w = len(self.issues['warning'])

        if c == 0 and w == 0:
            ok("No critical issues or warnings found")
            info("LVMS appears healthy")
            return

        if c:
            err(f"CRITICAL ISSUES: {c}")
            for i in self.issues['critical']:
                print(f"  - {i}")
            print()
        if w:
            warn(f"WARNINGS: {w}")
            for i in self.issues['warning']:
                print(f"  - {i}")
            print()

        section("RECOMMENDATIONS")
        if c:
            print(f"{BOLD}CRITICAL (Fix Immediately):{END}\n")
            if any('PVC' in i for i in self.issues['critical']):
                print("- Investigate pending PVCs: check VG status, free space, vg-manager pods")
            if any('not Ready' in i or 'Degraded' in i or 'Failed' in i for i in self.issues['critical']):
                print("- Fix LVMCluster/VG: check node devices, verify no conflicts, review vg-manager logs")
            if any('Pod' in i for i in self.issues['critical']):
                print("- Fix failing pods: review logs, check image pulls, verify node resources")
            print()
        if w:
            print(f"{BOLD}WARNINGS (Address Soon):{END}\n")
            if any('DaemonSet' in i for i in self.issues['warning']):
                print("- Investigate DaemonSet coverage: check node taints and tolerations")
            print()

    def run(self, component='all'):
        if not self.validate():
            return 1
        self.load_resources()
        self.load_pod_logs()

        if component in ('all', 'operator'):
            self.analyze_lvmcluster()
        if component in ('all', 'volumes', 'vg'):
            self.analyze_volume_groups()
        if component in ('all', 'storage', 'pvc'):
            self.analyze_pvcs()
        if component in ('all', 'operator', 'pods'):
            self.analyze_operator_health()
        if component in ('all', 'storage'):
            self.analyze_storage_classes()
        if component in ('all', 'operator', 'pods', 'logs'):
            self.analyze_pod_logs()

        self.summary()
        return 1 if self.issues['critical'] else 0


def main():
    parser = argparse.ArgumentParser(description='Analyze LVMS must-gather data')
    parser.add_argument('must_gather_path', help='Path to LVMS must-gather directory')
    parser.add_argument('--component',
                        choices=['all', 'storage', 'operator', 'volumes', 'vg', 'pvc', 'pods', 'logs'],
                        default='all', help='Component to analyze (default: all)')
    args = parser.parse_args()
    sys.exit(LVMSAnalyzer(args.must_gather_path).run(args.component))


if __name__ == '__main__':
    main()
