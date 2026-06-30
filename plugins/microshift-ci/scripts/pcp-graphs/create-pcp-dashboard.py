#!/usr/bin/env python3
"""Assemble a self-contained interactive PCP performance dashboard HTML.

Reads parsed JSON metric files from <workdir>/pcp-dashboard/<build_id>/<scenario>/
and scenario metadata from <workdir>/pcp-dashboard/scenarios.json.
Embeds Chart.js and all data inline — no external dependencies at runtime.

Usage:
    create-pcp-dashboard.py --workdir DIR [--timezone TZ]
"""

import argparse
import json
import os
import sys


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
VENDOR_DIR = os.path.join(SCRIPT_DIR, "vendor")

CSS = """\
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f0f2f5; color: #333; display: flex; height: 100vh; overflow: hidden; }
.sidebar { width: 300px; min-width: 300px; background: #1a1a2e; color: #e0e0e0; overflow-y: auto; padding: 16px 0; display: flex; flex-direction: column; }
.sidebar h1 { font-size: 1.1em; padding: 0 16px 12px; border-bottom: 1px solid #2a2a4e; color: #fff; }
.sidebar .build-group { margin-top: 12px; }
.sidebar .build-label { font-size: 0.75em; text-transform: uppercase; color: #8888aa; padding: 0 16px 4px; letter-spacing: 0.5px; }
.sidebar .scenario-item { padding: 8px 16px; cursor: pointer; font-size: 0.88em; display: flex; align-items: center; gap: 8px; transition: background 0.15s; border-left: 3px solid transparent; }
.sidebar .scenario-item:hover { background: #2a2a4e; }
.sidebar .scenario-item.active { background: #2a2a4e; border-left-color: #e94560; color: #fff; }
.sidebar .status-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.sidebar .status-dot.pass { background: #28a745; }
.sidebar .status-dot.fail { background: #dc3545; }
.sidebar .status-dot.unknown { background: #6c757d; }
.sidebar .scenario-name { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.sidebar .scenario-meta { font-size: 0.78em; color: #8888aa; margin-left: auto; white-space: nowrap; }
.main { flex: 1; overflow-y: auto; padding: 20px; }
.main h2 { font-size: 1.3em; color: #1a1a2e; margin-bottom: 4px; }
.scenario-info { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 16px; }
.info-card { background: #fff; border-radius: 8px; padding: 10px 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); display: flex; flex-direction: column; align-items: center; min-width: 100px; }
.info-card .value { font-size: 1.4em; font-weight: 700; }
.info-card .label { font-size: 0.78em; color: #6c757d; text-transform: uppercase; }
.info-card .value.pass { color: #28a745; }
.info-card .value.fail { color: #dc3545; }
.chart-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 20px; }
.chart-card { background: #fff; border-radius: 8px; padding: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
.chart-card h3 { font-size: 0.95em; color: #1a1a2e; margin-bottom: 8px; }
.chart-card canvas { width: 100% !important; height: 280px !important; }
.stats-row { display: flex; gap: 16px; flex-wrap: wrap; margin-top: 8px; font-size: 0.78em; color: #6c757d; }
.stats-row span { white-space: nowrap; }
.stats-row .val { font-weight: 600; color: #333; }
.empty-state { display: flex; flex-direction: column; align-items: center; justify-content: center; height: 60vh; color: #6c757d; }
.empty-state h2 { font-size: 1.3em; margin-bottom: 8px; }
@media (max-width: 900px) {
    .chart-grid { grid-template-columns: 1fr; }
    .sidebar { width: 220px; min-width: 220px; }
}
"""

JS_APP = """\
(function() {
    const DATA = __DATA_PLACEHOLDER__;
    const SCENARIOS = __SCENARIOS_PLACEHOLDER__;

    const sidebar = document.getElementById('sidebar-items');
    const mainArea = document.getElementById('main-area');
    let activeCharts = [];
    let activeKey = null;

    // Build sidebar
    const buildIds = Object.keys(DATA).sort();
    buildIds.forEach(function(bid) {
        const group = document.createElement('div');
        group.className = 'build-group';
        const label = document.createElement('div');
        label.className = 'build-label';
        label.textContent = 'Build ' + bid;
        group.appendChild(label);

        const scenarios = Object.keys(DATA[bid]).sort();
        scenarios.forEach(function(sc) {
            const meta = (SCENARIOS[bid] || {})[sc] || {};
            const item = document.createElement('div');
            item.className = 'scenario-item';
            item.dataset.key = bid + '/' + sc;

            const dot = document.createElement('span');
            dot.className = 'status-dot ' + (meta.status || 'unknown');
            item.appendChild(dot);

            const name = document.createElement('span');
            name.className = 'scenario-name';
            name.textContent = sc;
            name.title = sc;
            item.appendChild(name);

            if (meta.tests !== undefined) {
                const info = document.createElement('span');
                info.className = 'scenario-meta';
                info.textContent = meta.tests + 't';
                if (meta.failures > 0) info.textContent += ' ' + meta.failures + 'f';
                item.appendChild(info);
            }

            item.addEventListener('click', function() { selectScenario(bid, sc); });
            group.appendChild(item);
        });
        sidebar.appendChild(group);
    });

    // Select first scenario by default
    if (buildIds.length > 0) {
        const firstBid = buildIds[0];
        const firstSc = Object.keys(DATA[firstBid]).sort()[0];
        if (firstSc) selectScenario(firstBid, firstSc);
    }

    function selectScenario(bid, sc) {
        const key = bid + '/' + sc;
        if (key === activeKey) return;
        activeKey = key;

        document.querySelectorAll('.scenario-item').forEach(function(el) {
            el.classList.toggle('active', el.dataset.key === key);
        });

        // Destroy existing charts
        activeCharts.forEach(function(c) { c.destroy(); });
        activeCharts = [];

        mainArea.innerHTML = '';

        const metrics = DATA[bid][sc];
        const meta = (SCENARIOS[bid] || {})[sc] || {};

        // Header
        var h2 = document.createElement('h2');
        h2.textContent = sc;
        mainArea.appendChild(h2);

        // Info cards
        var infoRow = document.createElement('div');
        infoRow.className = 'scenario-info';
        infoRow.innerHTML = infoCard(meta.status === 'pass' ? 'PASS' : meta.status === 'fail' ? 'FAIL' : '?', 'Status', meta.status || 'unknown')
            + infoCard(meta.tests !== undefined ? meta.tests : '-', 'Tests', '')
            + infoCard(meta.failures !== undefined ? meta.failures : '-', 'Failures', meta.failures > 0 ? 'fail' : '')
            + infoCard(meta.duration_sec !== undefined ? formatDuration(meta.duration_sec) : '-', 'Duration', '')
            + infoCard(meta.vm_hosts ? meta.vm_hosts.join(', ') : '-', 'VM Host', '');
        mainArea.appendChild(infoRow);

        // Chart grid
        var grid = document.createElement('div');
        grid.className = 'chart-grid';
        mainArea.appendChild(grid);

        if (metrics.cpu) renderCpu(grid, metrics.cpu);
        if (metrics.mem) renderMem(grid, metrics.mem);
        if (metrics.io) renderIo(grid, metrics.io);
        if (metrics.disk) renderDisk(grid, metrics.disk);

        if (!metrics.cpu && !metrics.mem && !metrics.io && !metrics.disk) {
            grid.innerHTML = '<div class="chart-card" style="grid-column:1/-1;text-align:center;padding:40px;color:#6c757d;">No PCP metric data available for this scenario.</div>';
        }
    }

    function infoCard(value, label, cls) {
        return '<div class="info-card"><span class="value ' + cls + '">' + value + '</span><span class="label">' + label + '</span></div>';
    }

    function formatDuration(sec) {
        if (sec < 60) return sec + 's';
        var m = Math.floor(sec / 60);
        var s = Math.round(sec % 60);
        if (m < 60) return m + 'm ' + s + 's';
        var h = Math.floor(m / 60);
        m = m % 60;
        return h + 'h ' + m + 'm';
    }

    function makeCard(grid, title) {
        var card = document.createElement('div');
        card.className = 'chart-card';
        var h3 = document.createElement('h3');
        h3.textContent = title;
        card.appendChild(h3);
        var canvas = document.createElement('canvas');
        card.appendChild(canvas);
        grid.appendChild(card);
        return { card: card, canvas: canvas };
    }

    function addStats(card, items) {
        var row = document.createElement('div');
        row.className = 'stats-row';
        items.forEach(function(it) {
            row.innerHTML += '<span>' + it.label + ': <span class="val">' + it.value + '</span></span>';
        });
        card.appendChild(row);
    }

    function peak(arr) { return arr.length ? Math.max.apply(null, arr) : 0; }
    function avg(arr) { return arr.length ? arr.reduce(function(a,b){return a+b;},0) / arr.length : 0; }

    function renderCpu(grid, d) {
        var c = makeCard(grid, 'CPU Usage');
        var chart = new Chart(c.canvas, {
            type: 'line',
            data: {
                labels: d.timestamps,
                datasets: [
                    { label: 'User', data: d.user, borderColor: '#3b82f6', backgroundColor: 'rgba(59,130,246,0.15)', fill: true, pointRadius: 0, borderWidth: 1.5, tension: 0.2, order: 3 },
                    { label: 'I/O Wait', data: d.iowait, borderColor: '#f59e0b', backgroundColor: 'rgba(245,158,11,0.15)', fill: true, pointRadius: 0, borderWidth: 1.5, tension: 0.2, order: 2 },
                    { label: 'System', data: d.sys, borderColor: '#ef4444', backgroundColor: 'rgba(239,68,68,0.15)', fill: true, pointRadius: 0, borderWidth: 1.5, tension: 0.2, order: 1 }
                ]
            },
            options: cpuMemOpts('CPU %', 100)
        });
        activeCharts.push(chart);
        addStats(c.card, [
            { label: 'Peak User', value: peak(d.user).toFixed(1) + '%' },
            { label: 'Peak System', value: peak(d.sys).toFixed(1) + '%' },
            { label: 'Peak I/O Wait', value: peak(d.iowait).toFixed(1) + '%' },
            { label: 'Avg Total', value: avg(d.user.map(function(v,i){return v + d.sys[i] + d.iowait[i];})).toFixed(1) + '%' }
        ]);
    }

    function renderMem(grid, d) {
        var c = makeCard(grid, 'Memory Usage');
        var datasets = [
            { label: 'Used', data: d.used_gb, borderColor: '#ef4444', backgroundColor: 'rgba(239,68,68,0.15)', fill: true, pointRadius: 0, borderWidth: 1.5, tension: 0.2, order: 2 },
            { label: 'Cached', data: d.cached_gb, borderColor: '#f59e0b', backgroundColor: 'rgba(245,158,11,0.15)', fill: true, pointRadius: 0, borderWidth: 1.5, tension: 0.2, order: 1 }
        ];
        if (d.total_gb && d.total_gb.length) {
            datasets.push({ label: 'Total', data: d.total_gb, borderColor: '#333', backgroundColor: 'transparent', fill: false, pointRadius: 0, borderWidth: 1.5, borderDash: [5,3], tension: 0, order: 0 });
        }
        var maxY = d.total_gb && d.total_gb.length ? Math.ceil(Math.max.apply(null, d.total_gb) * 1.1) : undefined;
        var chart = new Chart(c.canvas, {
            type: 'line',
            data: { labels: d.timestamps, datasets: datasets },
            options: cpuMemOpts('GB', maxY)
        });
        activeCharts.push(chart);
        addStats(c.card, [
            { label: 'Peak Used', value: peak(d.used_gb).toFixed(2) + ' GB' },
            { label: 'Peak Cached', value: peak(d.cached_gb).toFixed(2) + ' GB' },
            { label: 'Total', value: d.total_gb && d.total_gb.length ? d.total_gb[0].toFixed(2) + ' GB' : '-' }
        ]);
    }

    function renderIo(grid, d) {
        var c = makeCard(grid, 'Disk I/O');
        var chart = new Chart(c.canvas, {
            type: 'line',
            data: {
                labels: d.timestamps,
                datasets: [
                    { label: 'Read OPS', data: d.bi, borderColor: '#3b82f6', backgroundColor: 'transparent', fill: false, pointRadius: 0, borderWidth: 1.5, tension: 0.2, yAxisID: 'y' },
                    { label: 'Write OPS', data: d.bo, borderColor: '#ef4444', backgroundColor: 'transparent', fill: false, pointRadius: 0, borderWidth: 1.5, tension: 0.2, yAxisID: 'y' },
                    { label: 'Await (ms)', data: d.await, borderColor: '#22c55e', backgroundColor: 'transparent', fill: false, pointRadius: 0, borderWidth: 1.5, borderDash: [5,3], tension: 0.2, yAxisID: 'y1' }
                ]
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                plugins: { legend: { position: 'bottom', labels: { boxWidth: 12, font: { size: 11 } } }, tooltip: { mode: 'index', intersect: false } },
                scales: {
                    x: { ticks: { maxTicksLimit: 8, maxRotation: 0, font: { size: 10 } }, grid: { display: false } },
                    y: { position: 'left', title: { display: true, text: 'OPS', font: { size: 11 } }, beginAtZero: true, ticks: { font: { size: 10 } } },
                    y1: { position: 'right', title: { display: true, text: 'Await (ms)', font: { size: 11 } }, beginAtZero: true, grid: { drawOnChartArea: false }, ticks: { font: { size: 10 } } }
                }
            }
        });
        activeCharts.push(chart);
        addStats(c.card, [
            { label: 'Peak Read', value: peak(d.bi).toFixed(0) + ' OPS' },
            { label: 'Peak Write', value: peak(d.bo).toFixed(0) + ' OPS' },
            { label: 'Peak Await', value: peak(d.await).toFixed(1) + ' ms' },
            { label: 'Peak Queue', value: peak(d.aveq).toFixed(2) }
        ]);
    }

    function renderDisk(grid, d) {
        var c = makeCard(grid, 'Disk Usage');
        var colors = ['#8b5cf6','#3b82f6','#22c55e','#f59e0b','#ef4444','#ec4899','#06b6d4','#84cc16'];
        var datasets = d.partitions.map(function(p, i) {
            var lbl = p.device;
            if (p.mountdir) lbl += ' (' + p.mountdir + ')';
            if (p.capacity_gb) lbl += ' ' + p.capacity_gb + 'G';
            return {
                label: lbl, data: p.used_pct,
                borderColor: colors[i % colors.length], backgroundColor: 'transparent',
                fill: false, pointRadius: 0, borderWidth: 1.5, tension: 0.2
            };
        });
        var chart = new Chart(c.canvas, {
            type: 'line',
            data: { labels: d.timestamps, datasets: datasets },
            options: cpuMemOpts('Usage %', 100)
        });
        activeCharts.push(chart);
        var statsItems = d.partitions.map(function(p) {
            var pctArr = p.used_pct.filter(function(v) { return v !== null; });
            return { label: 'Peak ' + (p.mountdir || p.device), value: peak(pctArr).toFixed(1) + '%' };
        });
        addStats(c.card, statsItems.slice(0, 4));
    }

    function cpuMemOpts(yLabel, yMax) {
        return {
            responsive: true, maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: { legend: { position: 'bottom', labels: { boxWidth: 12, font: { size: 11 } } }, tooltip: { mode: 'index', intersect: false } },
            scales: {
                x: { ticks: { maxTicksLimit: 8, maxRotation: 0, font: { size: 10 } }, grid: { display: false } },
                y: { beginAtZero: true, max: yMax, title: { display: true, text: yLabel, font: { size: 11 } }, ticks: { font: { size: 10 } } }
            }
        };
    }
})();
"""


def load_chartjs():
    """Load the vendored Chart.js UMD bundle."""
    path = os.path.join(VENDOR_DIR, "chart.umd.min.js")
    if not os.path.isfile(path):
        print(f"ERROR: Chart.js not found at {path}", file=sys.stderr)
        print("Run: curl -sL https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js "
              f"-o {path}", file=sys.stderr)
        sys.exit(1)
    with open(path) as f:
        return f.read()


def load_metrics(dashboard_dir):
    """Load all parsed metric JSON files, grouped by build_id and scenario."""
    data = {}
    if not os.path.isdir(dashboard_dir):
        return data

    for build_id in sorted(os.listdir(dashboard_dir)):
        build_path = os.path.join(dashboard_dir, build_id)
        if not os.path.isdir(build_path) or build_id == "scenarios.json":
            continue
        for scenario in sorted(os.listdir(build_path)):
            scenario_path = os.path.join(build_path, scenario)
            if not os.path.isdir(scenario_path):
                continue

            metrics = {}
            for name, key in [("cpu.json", "cpu"), ("mem.json", "mem"),
                               ("io.json", "io"), ("disk.json", "disk")]:
                fpath = os.path.join(scenario_path, name)
                if os.path.isfile(fpath):
                    try:
                        with open(fpath) as f:
                            metrics[key] = json.load(f)
                    except (json.JSONDecodeError, IOError):
                        pass

            if metrics:
                data.setdefault(build_id, {})[scenario] = metrics

    return data


def load_scenarios(dashboard_dir):
    """Load scenario metadata."""
    path = os.path.join(dashboard_dir, "scenarios.json")
    if os.path.isfile(path):
        with open(path) as f:
            return json.load(f)
    return {}


def build_html(chartjs_src, data_json, scenarios_json, timezone):
    """Assemble the complete HTML document."""
    js_app = JS_APP.replace("__DATA_PLACEHOLDER__", data_json)
    js_app = js_app.replace("__SCENARIOS_PLACEHOLDER__", scenarios_json)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PCP Performance Dashboard</title>
<style>
{CSS}
</style>
</head>
<body>
<div class="sidebar">
    <h1>PCP Dashboard</h1>
    <div style="padding:4px 16px;font-size:0.75em;color:#8888aa;">Timezone: {timezone}</div>
    <div id="sidebar-items"></div>
</div>
<div class="main" id="main-area">
    <div class="empty-state">
        <h2>Select a scenario</h2>
        <p>Choose a scenario from the sidebar to view performance metrics.</p>
    </div>
</div>
<script>
{chartjs_src}
</script>
<script>
{js_app}
</script>
</body>
</html>"""


def main():
    parser = argparse.ArgumentParser(
        description="Generate interactive PCP performance dashboard HTML")
    parser.add_argument("--workdir", required=True,
                        help="Work directory with pcp-dashboard/ subdirectory")
    parser.add_argument("--timezone", default="UTC",
                        help="Timezone label for display (default: UTC)")
    parser.add_argument("--output",
                        help="Output HTML file (default: <workdir>/pcp-dashboard.html)")
    args = parser.parse_args()

    dashboard_dir = os.path.join(args.workdir, "pcp-dashboard")
    output = args.output or os.path.join(args.workdir, "pcp-dashboard.html")

    chartjs_src = load_chartjs()
    data = load_metrics(dashboard_dir)
    scenarios = load_scenarios(dashboard_dir)

    if not data:
        print("WARNING: No PCP metric data found in "
              f"{dashboard_dir}", file=sys.stderr)

    data_json = json.dumps(data, separators=(",", ":"))
    scenarios_json = json.dumps(scenarios, separators=(",", ":"))

    html = build_html(chartjs_src, data_json, scenarios_json, args.timezone)

    with open(output, "w") as f:
        f.write(html)

    total_scenarios = sum(len(v) for v in data.values())
    print(f"Dashboard generated: {output} "
          f"({total_scenarios} scenarios, {len(html)//1024}KB)",
          file=sys.stderr)


if __name__ == "__main__":
    main()
