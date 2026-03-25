"""Configuration loading."""

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .models import Topology

DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"


@dataclass
class JiraConfig:
    project: str = "OCPBUGS"
    component: str = "Edge Enablement"


@dataclass
class OutputConfig:
    report_dir: str = "./reports"


@dataclass
class SlackConfig:
    webhook_url: str = ""
    channel: str = ""
    enabled: bool = False


@dataclass
class VersionsConfig:
    auto_discover: bool = True
    override: list[str] = field(default_factory=list)


@dataclass
class Config:
    versions: VersionsConfig = field(default_factory=VersionsConfig)
    topologies: list[Topology] = field(default_factory=list)
    payloads_per_stream: int = 5
    jira: JiraConfig = field(default_factory=JiraConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    slack: SlackConfig = field(default_factory=SlackConfig)


def load_config(path: Path | None = None) -> Config:
    config_path = path or DEFAULT_CONFIG_PATH
    if not config_path.exists():
        return _default_config()

    with open(config_path) as f:
        raw = yaml.safe_load(f) or {}

    return _parse_config(raw)


def _default_config() -> Config:
    return Config(
        topologies=[
            Topology("SNO", ["sno", "single-node", "metal-single-node"], ["telco"]),
            Topology("TNA", ["two-node", "tna"], ["telco"]),
            Topology("TNF", ["tnf", "two-node-fencing"], ["telco"]),
        ]
    )


def _parse_config(raw: dict) -> Config:
    versions_raw = raw.get("versions", {})
    versions = VersionsConfig(
        auto_discover=versions_raw.get("auto_discover", True),
        override=versions_raw.get("override", []),
    )

    topologies = []
    for t in raw.get("topologies", []):
        topologies.append(Topology(
            name=t["name"],
            job_patterns=t.get("job_patterns", []),
            exclude_patterns=t.get("exclude_patterns", []),
        ))
    if not topologies:
        topologies = _default_config().topologies

    jira_raw = raw.get("jira", {})
    jira = JiraConfig(
        project=jira_raw.get("project", "OCPBUGS"),
        component=jira_raw.get("component", "Edge Enablement"),
    )

    output_raw = raw.get("output", {})
    output = OutputConfig(report_dir=output_raw.get("report_dir", "./reports"))

    slack_raw = raw.get("slack", {})
    slack = SlackConfig(
        webhook_url=slack_raw.get("webhook_url", ""),
        channel=slack_raw.get("channel", ""),
        enabled=slack_raw.get("enabled", False),
    )

    return Config(
        versions=versions,
        topologies=topologies,
        payloads_per_stream=raw.get("payloads_per_stream", 5),
        jira=jira,
        output=output,
        slack=slack,
    )
