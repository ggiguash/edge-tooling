"""Data models for payload monitoring."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class PayloadStatus(Enum):
    ACCEPTED = "Accepted"
    REJECTED = "Rejected"
    PENDING = "Pending"


class JobType(Enum):
    BLOCKING = "blocking"
    INFORMING = "informing"


class JobResult(Enum):
    SUCCESS = "S"
    FAILURE = "F"
    PENDING = "P"
    UNKNOWN = "U"


@dataclass
class Topology:
    name: str
    job_patterns: list[str]
    exclude_patterns: list[str] = field(default_factory=list)

    def matches(self, job_name: str) -> bool:
        job_lower = job_name.lower()
        if any(p in job_lower for p in self.exclude_patterns):
            return False
        return any(p in job_lower for p in self.job_patterns)


@dataclass
class DeepAnalysis:
    root_cause: str = ""
    failure_type: str = ""
    impact: str = ""
    suspect_prs: list[str] = field(default_factory=list)
    recommendation: str = ""


@dataclass
class FailingTest:
    name: str
    error_message: str = ""
    duration_seconds: float = 0.0


@dataclass
class JobRun:
    name: str
    url: str
    result: JobResult
    job_type: JobType
    topology: Optional[str] = None
    prow_url: str = ""
    failing_tests: list[FailingTest] = field(default_factory=list)
    error_summary: str = ""
    deep_analysis: Optional[DeepAnalysis] = None


@dataclass
class Payload:
    tag: str
    stream: str
    version: str
    status: PayloadStatus
    phase: str = ""
    url: str = ""
    jobs: list[JobRun] = field(default_factory=list)

    @property
    def edge_jobs(self) -> list[JobRun]:
        return [j for j in self.jobs if j.topology is not None]

    @property
    def failing_edge_jobs(self) -> list[JobRun]:
        return [j for j in self.edge_jobs if j.result == JobResult.FAILURE]


@dataclass
class Regression:
    test_name: str
    test_id: str
    component: str
    capability: str
    basis_pass_rate: float
    sample_pass_rate: float
    variant: str = ""
    topology: str = ""
    triage_url: str = ""
    jira_bug: str = ""
    current_runs: int = 0


@dataclass
class ComponentRegression:
    component: str
    test_name: str
    test_suite: str
    test_id: str
    capability: str
    version: str
    variants: dict = field(default_factory=dict)
    status: int = 0
    sample_success: int = 0
    sample_failure: int = 0
    sample_pass_rate: float = 0.0
    base_success: int = 0
    base_failure: int = 0
    base_pass_rate: float = 0.0
    fisher_exact: float = 0.0
    last_failure: str = ""
    detail_url: str = ""
    explanation: str = ""


@dataclass
class JiraBug:
    key: str
    summary: str
    status: str
    assignee: str = ""
    priority: str = ""
    url: str = ""
    component: str = ""


@dataclass
class SuggestedBug:
    title: str
    description: str
    job_name: str
    topology: str
    version: str
    failing_tests: list[str] = field(default_factory=list)
    create_url: str = ""


@dataclass
class StreamReport:
    stream: str
    version: str
    payloads: list[Payload] = field(default_factory=list)
    regressions: list[Regression] = field(default_factory=list)

    @property
    def latest_payload(self) -> Optional[Payload]:
        return self.payloads[0] if self.payloads else None

    @property
    def total_edge_failures(self) -> int:
        return sum(len(p.failing_edge_jobs) for p in self.payloads)


@dataclass
class MonitorReport:
    generated_at: str = ""
    streams: list[StreamReport] = field(default_factory=list)
    jira_bugs: list[JiraBug] = field(default_factory=list)
    suggested_bugs: list[SuggestedBug] = field(default_factory=list)
    component_regressions: list[ComponentRegression] = field(default_factory=list)
    ai_cost: str = ""
    skip_prow: bool = False
    skip_sippy: bool = False
    skip_jira: bool = False
