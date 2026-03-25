"""Generate HTML dashboard report from monitor data."""

import json
import logging
import re
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from ..models import (
    ComponentRegression,
    DeepAnalysis,
    FailingTest,
    JobResult,
    JobRun,
    JobType,
    JiraBug,
    MonitorReport,
    Payload,
    PayloadStatus,
    Regression,
    StreamReport,
    SuggestedBug,
)

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent / "templates"

_TAG_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})-(\d{2})(\d{2})(\d{2})$")


def _extract_date(tag: str) -> str:
    """Extract date and time from a payload tag like '4.19.0-0.nightly-2026-03-25-085944'."""
    m = _TAG_DATE_RE.search(tag)
    if not m:
        return ""
    return f"{m.group(1)} {m.group(2)}:{m.group(3)}:{m.group(4)}"


def _build_template_context(report: MonitorReport) -> dict:
    """Build the Jinja2 template context from a MonitorReport."""
    # Collect all failing edge jobs with their context
    all_failing = []
    failure_details = []
    for stream in report.streams:
        for payload in stream.payloads:
            for job in payload.failing_edge_jobs:
                item = {
                    "job": job,
                    "version": stream.version,
                    "payload_tag": payload.tag,
                    "payload_url": payload.url,
                    "date": _extract_date(payload.tag),
                }
                all_failing.append(item)
                if job.failing_tests:
                    failure_details.append(item)

    # Collect all regressions
    all_regressions = []
    for stream in report.streams:
        for r in stream.regressions:
            r_with_version = Regression(
                test_name=r.test_name,
                test_id=r.test_id,
                component=r.component,
                capability=r.capability,
                basis_pass_rate=r.basis_pass_rate,
                sample_pass_rate=r.sample_pass_rate,
                topology=r.topology,
                triage_url=r.triage_url,
                jira_bug=r.jira_bug,
                current_runs=r.current_runs,
            )
            r_with_version.version = stream.version  # type: ignore
            all_regressions.append(r_with_version)

    # Unique topology names and versions for filters
    topologies = sorted(set(
        job["job"].topology for job in all_failing if job["job"].topology
    ))
    versions = sorted(set(stream.version for stream in report.streams))

    return {
        "report": report,
        "all_failing": all_failing,
        "failure_details": failure_details,
        "all_regressions": sorted(
            all_regressions,
            key=lambda r: r.sample_pass_rate - r.basis_pass_rate,
        ),
        "component_regressions": sorted(
            report.component_regressions,
            key=lambda cr: cr.sample_pass_rate - cr.base_pass_rate,
        ),
        "cr_platforms": sorted(set(
            cr.variants.get("Platform", "") for cr in report.component_regressions
            if cr.variants.get("Platform")
        )),
        "cr_versions": sorted(set(
            cr.version for cr in report.component_regressions
        )),
        "topologies": topologies,
        "versions": versions,
    }


def generate_html(report: MonitorReport, output_path: Path | None = None) -> str:
    """Generate a self-contained HTML report.

    Returns the HTML content as a string. If output_path is provided,
    also writes to that file.
    """
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=False,
    )

    # Load CSS and JS to inline
    css = (TEMPLATES_DIR / "styles.css").read_text()
    js = (TEMPLATES_DIR / "scripts.js").read_text()

    template = env.get_template("dashboard.html")
    context = _build_template_context(report)
    context["css"] = css
    context["js"] = js

    html = template.render(**context)

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html)
        logger.info(f"Report written to {output_path}")

    return html


def generate_json(report: MonitorReport, output_path: Path) -> None:
    """Export report data as JSON for external consumption."""
    data = {
        "generated_at": report.generated_at,
        "ai_cost": report.ai_cost,
        "streams": [],
        "jira_bugs": [asdict(b) for b in report.jira_bugs],
        "suggested_bugs": [asdict(b) for b in report.suggested_bugs],
        "component_regressions": [asdict(cr) for cr in report.component_regressions],
    }

    for stream in report.streams:
        stream_data = {
            "stream": stream.stream,
            "version": stream.version,
            "total_edge_failures": stream.total_edge_failures,
            "payloads": [],
            "regressions": [asdict(r) for r in stream.regressions],
        }
        for payload in stream.payloads:
            payload_data = {
                "tag": payload.tag,
                "status": payload.status.value,
                "phase": payload.phase,
                "url": payload.url,
                "edge_jobs": [
                    {
                        "name": j.name,
                        "result": j.result.value,
                        "job_type": j.job_type.value,
                        "topology": j.topology,
                        "prow_url": j.prow_url,
                        "error_summary": j.error_summary,
                        "failing_tests": [
                            {"name": t.name, "error": t.error_message}
                            for t in j.failing_tests
                        ],
                        "deep_analysis": asdict(j.deep_analysis) if j.deep_analysis else None,
                    }
                    for j in payload.edge_jobs
                ],
            }
            stream_data["payloads"].append(payload_data)
        data["streams"].append(stream_data)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(data, indent=2))
    logger.info(f"JSON data written to {output_path}")

    # Generate a small blocking-failures summary for the skill to read
    blocking_summary = []
    for stream in report.streams:
        for payload in stream.payloads:
            for job in payload.failing_edge_jobs:
                if job.job_type == JobType.BLOCKING:
                    blocking_summary.append({
                        "job_name": job.name,
                        "prow_url": job.prow_url,
                        "topology": job.topology,
                        "version": stream.version,
                        "payload_tag": payload.tag,
                    })
    if blocking_summary:
        blocking_path = output_path.with_suffix(".blocking.json")
        blocking_path.write_text(json.dumps(blocking_summary, indent=2))
        logger.info(f"Blocking summary written to {blocking_path}")


def merge_analysis(report: MonitorReport, analysis_path: Path) -> None:
    """Merge a small analysis-only JSON into a MonitorReport.

    The analysis JSON is keyed by prow_url:
    {
      "by_prow_url": {
        "https://prow.ci.../123": {
          "root_cause": "...",
          "failure_type": "...",
          "impact": "...",
          "suspect_prs": [],
          "recommendation": "..."
        }
      }
    }
    """
    with open(analysis_path) as f:
        data = json.load(f)

    by_url = data.get("by_prow_url", {})
    merged = 0
    for stream in report.streams:
        for payload in stream.payloads:
            for job in payload.jobs:
                if job.prow_url in by_url:
                    da = by_url[job.prow_url]
                    job.deep_analysis = DeepAnalysis(
                        root_cause=da.get("root_cause", ""),
                        failure_type=da.get("failure_type", ""),
                        impact=da.get("impact", ""),
                        suspect_prs=da.get("suspect_prs", []),
                        recommendation=da.get("recommendation", ""),
                    )
                    merged += 1

    # Pick up optional ai_cost field
    if data.get("ai_cost"):
        report.ai_cost = data["ai_cost"]

    logger.info(f"Merged deep analysis for {merged} job(s)")


def load_json(json_path: Path) -> MonitorReport:
    """Load a MonitorReport from a JSON file (potentially enriched with deep analysis)."""
    with open(json_path) as f:
        data = json.load(f)

    streams = []
    for s in data.get("streams", []):
        payloads = []
        for p in s.get("payloads", []):
            jobs = []
            for j in p.get("edge_jobs", []):
                da_raw = j.get("deep_analysis")
                deep_analysis = None
                if da_raw:
                    deep_analysis = DeepAnalysis(
                        root_cause=da_raw.get("root_cause", ""),
                        failure_type=da_raw.get("failure_type", ""),
                        impact=da_raw.get("impact", ""),
                        suspect_prs=da_raw.get("suspect_prs", []),
                        recommendation=da_raw.get("recommendation", ""),
                    )
                failing_tests = [
                    FailingTest(name=t.get("name", ""), error_message=t.get("error", ""))
                    for t in j.get("failing_tests", [])
                ]
                jobs.append(JobRun(
                    name=j.get("name", ""),
                    url=j.get("prow_url", ""),
                    result=JobResult(j.get("result", "U")),
                    job_type=JobType(j.get("job_type", "informing")),
                    topology=j.get("topology"),
                    prow_url=j.get("prow_url", ""),
                    failing_tests=failing_tests,
                    error_summary=j.get("error_summary", ""),
                    deep_analysis=deep_analysis,
                ))
            payloads.append(Payload(
                tag=p.get("tag", ""),
                stream=s.get("stream", ""),
                version=s.get("version", ""),
                status=PayloadStatus(p.get("status", "Pending")),
                phase=p.get("phase", ""),
                url=p.get("url", ""),
                jobs=jobs,
            ))

        regressions = []
        for r in s.get("regressions", []):
            regressions.append(Regression(
                test_name=r.get("test_name", ""),
                test_id=r.get("test_id", ""),
                component=r.get("component", ""),
                capability=r.get("capability", ""),
                basis_pass_rate=r.get("basis_pass_rate", 0),
                sample_pass_rate=r.get("sample_pass_rate", 0),
                topology=r.get("topology", ""),
                triage_url=r.get("triage_url", ""),
                jira_bug=r.get("jira_bug", ""),
                current_runs=r.get("current_runs", 0),
            ))

        streams.append(StreamReport(
            stream=s.get("stream", ""),
            version=s.get("version", ""),
            payloads=payloads,
            regressions=regressions,
        ))

    jira_bugs = [
        JiraBug(**b) for b in data.get("jira_bugs", [])
    ]
    suggested_bugs = [
        SuggestedBug(**b) for b in data.get("suggested_bugs", [])
    ]
    comp_regressions = [
        ComponentRegression(**cr) for cr in data.get("component_regressions", [])
    ]

    return MonitorReport(
        generated_at=data.get("generated_at", ""),
        streams=streams,
        jira_bugs=jira_bugs,
        suggested_bugs=suggested_bugs,
        component_regressions=comp_regressions,
        ai_cost=data.get("ai_cost", ""),
    )
