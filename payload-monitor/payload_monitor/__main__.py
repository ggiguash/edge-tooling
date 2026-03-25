"""CLI entry point for Edge Payload Monitor."""

import logging
import subprocess
import sys
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

import click

from .analyzer import analyze
from .collectors import component_readiness, prow, sippy
from .collectors.release_controller import collect as collect_payloads
from .config import load_config
from .models import MonitorReport
from .report.generator import generate_html, generate_json, load_json, merge_analysis


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-5s %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )


@click.command()
@click.option("--config", "config_path", type=click.Path(exists=True), default=None,
              help="Config file path (default: config.yaml)")
@click.option("--versions", type=str, default=None,
              help="Override versions, comma-separated (e.g., '4.18,4.19')")
@click.option("--output", "output_path", type=click.Path(), default=None,
              help="Output HTML file path")
@click.option("--from-json", "from_json", type=click.Path(exists=True), default=None,
              help="Regenerate HTML from an enriched JSON file (skips data collection)")
@click.option("--open", "open_browser", is_flag=True, default=False,
              help="Open report in browser after generation")
@click.option("--verbose", is_flag=True, default=False,
              help="Enable verbose logging")
@click.option("--skip-prow", is_flag=True, default=False,
              help="Skip Prow artifact fetching (faster, less detail)")
@click.option("--skip-sippy", is_flag=True, default=False,
              help="Skip Sippy regression check")
@click.option("--merge-analysis", "merge_analysis_path", type=click.Path(exists=True), default=None,
              help="Merge a small analysis JSON (keyed by prow_url) into the report loaded via --from-json")
def main(
    config_path, versions, output_path, from_json,
    open_browser, verbose, skip_prow, skip_sippy, merge_analysis_path,
):
    """Edge Payload Monitor — monitor OpenShift nightly payloads for edge topology failures."""
    _setup_logging(verbose)
    logger = logging.getLogger("payload_monitor")

    # Load config
    config = load_config(Path(config_path) if config_path else None)

    # Determine output path
    if not output_path:
        report_dir = Path(config.output.report_dir)
        date_str = datetime.now().strftime("%Y-%m-%d")
        output_path = str(report_dir / f"report-{date_str}.html")
    html_path = Path(output_path)

    # --from-json mode: regenerate HTML from JSON, optionally merging analysis data
    if from_json:
        logger.info(f"Loading report from {from_json}")
        report = load_json(Path(from_json))
        if merge_analysis_path:
            logger.info(f"Merging analysis from {merge_analysis_path}")
            merge_analysis(report, Path(merge_analysis_path))
        generate_html(report, html_path)
        logger.info(f"Report regenerated: {html_path.resolve()}")
        if open_browser:
            webbrowser.open(f"file://{html_path.resolve()}")
        return

    # Override versions if specified
    if versions:
        config.versions.auto_discover = False
        config.versions.override = [v.strip() for v in versions.split(",")]

    logger.info("Starting Edge Payload Monitor")

    # Step 1: Collect payload data from release controller
    logger.info("Step 1/5: Fetching payloads from release controller...")
    stream_reports = collect_payloads(config)

    # Step 2: Enrich failing jobs with Prow data
    if not skip_prow:
        logger.info("Step 2/5: Fetching Prow artifacts for failing jobs...")
        for stream in stream_reports:
            for payload in stream.payloads:
                prow.enrich_failing_jobs(payload.jobs)
    else:
        logger.info("Step 2/5: Skipping Prow enrichment (--skip-prow)")

    # Step 3: Fetch Sippy regressions + Component Readiness
    comp_regs = []
    if not skip_sippy:
        logger.info("Step 3/5: Checking Sippy for job regressions...")
        active_versions = [s.version for s in stream_reports]
        sippy_regressions = sippy.collect(config, active_versions)
        for stream in stream_reports:
            stream.regressions = sippy_regressions.get(stream.version, [])

        logger.info("Step 4/5: Checking Component Readiness (HA vs Single Node)...")
        comp_regs = component_readiness.collect(active_versions)
    else:
        logger.info("Step 3/5: Skipping Sippy check (--skip-sippy)")
        logger.info("Step 4/5: Skipping Component Readiness (--skip-sippy)")

    # Build report
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    report = MonitorReport(
        generated_at=now,
        streams=stream_reports,
        component_regressions=comp_regs,
        skip_prow=skip_prow,
        skip_sippy=skip_sippy,
    )

    # Step 5: Analyze and find JIRA matches
    logger.info("Step 5/5: Analyzing failures and searching JIRA...")
    analyze(report, config)

    # Generate output (always HTML + JSON)
    generate_html(report, html_path)
    json_path = html_path.with_suffix(".json")
    generate_json(report, json_path)

    # Summary
    total_edge_failures = sum(s.total_edge_failures for s in report.streams)
    total_regressions = sum(len(s.regressions) for s in report.streams)
    logger.info(f"Done. {total_edge_failures} edge failures, {total_regressions} regressions")
    logger.info(f"Report: {html_path.resolve()}")
    logger.info(f"JSON:   {json_path.resolve()}")

    if open_browser:
        webbrowser.open(f"file://{html_path.resolve()}")


if __name__ == "__main__":
    main()
