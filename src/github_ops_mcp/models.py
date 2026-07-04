"""Pydantic models for all github-ops-mcp tool outputs."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Shared / primitive models
# ---------------------------------------------------------------------------


class IssueSummary(BaseModel):
    number: int
    title: str
    url: str
    created_at: datetime
    updated_at: datetime
    labels: list[str] = []
    assignee: Optional[str] = None
    milestone: Optional[str] = None

    def __str__(self) -> str:
        parts = []
        if self.assignee:
            parts.append(f"assignee: {self.assignee}")
        if self.labels:
            parts.append(f"labels: {', '.join(self.labels)}")
        if self.milestone:
            parts.append(f"milestone: {self.milestone}")
        detail = f" ({', '.join(parts)})" if parts else ""
        return f"#{self.number} {self.title}{detail}"


class PRSummary(BaseModel):
    number: int
    title: str
    url: str
    author: str
    created_at: datetime
    updated_at: datetime
    review_status: str
    reviewers: list[str] = []
    days_waiting: int

    def __str__(self) -> str:
        reviewers_str = f", reviewers: {', '.join(self.reviewers)}" if self.reviewers else ""
        return (
            f"#{self.number} {self.title} by {self.author} "
            f"({self.review_status}, {self.days_waiting}d waiting{reviewers_str})"
        )


class HealthCheck(BaseModel):
    name: str
    passed: bool
    detail: str

    def __str__(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        return f"[{status}] {self.name}: {self.detail}"


class UserPermission(BaseModel):
    login: str
    permission: str
    source: str

    def __str__(self) -> str:
        return f"{self.login} ({self.permission}, via {self.source})"


class CheckResult(BaseModel):
    name: str
    status: str
    url: Optional[str] = None

    def __str__(self) -> str:
        return f"  [{self.status.upper()}] {self.name}"


class PRCheckSummary(BaseModel):
    number: int
    title: str
    checks: list[CheckResult] = []
    passing: int
    failing: int
    pending: int

    def __str__(self) -> str:
        checks_str = "\n".join(str(c) for c in self.checks)
        summary = f"#{self.number} {self.title} — pass:{self.passing} fail:{self.failing} pending:{self.pending}"
        if checks_str:
            return f"{summary}\n{checks_str}"
        return summary


class AuditFinding(BaseModel):
    repo: str
    finding: str
    severity: str
    users: list[str] = []

    def __str__(self) -> str:
        users_str = f" (users: {', '.join(self.users)})" if self.users else ""
        return f"[{self.severity.upper()}] {self.repo}: {self.finding}{users_str}"


# ---------------------------------------------------------------------------
# Issue tool outputs
# ---------------------------------------------------------------------------


class TriageReport(BaseModel):
    repo: str
    total_untriaged: int
    missing_labels: list[IssueSummary] = []
    missing_assignee: list[IssueSummary] = []
    missing_milestone: list[IssueSummary] = []

    def __str__(self) -> str:
        lines = [
            f"Triage Report: {self.repo}",
            f"Total untriaged: {self.total_untriaged}",
        ]
        if self.missing_labels:
            lines.append(f"\nMissing labels ({len(self.missing_labels)}):")
            lines.extend(f"  {issue}" for issue in self.missing_labels)
        if self.missing_assignee:
            lines.append(f"\nMissing assignee ({len(self.missing_assignee)}):")
            lines.extend(f"  {issue}" for issue in self.missing_assignee)
        if self.missing_milestone:
            lines.append(f"\nMissing milestone ({len(self.missing_milestone)}):")
            lines.extend(f"  {issue}" for issue in self.missing_milestone)
        return "\n".join(lines)


class BulkLabelResult(BaseModel):
    repo: str
    label: str
    filter_text: str
    affected: list[IssueSummary] = []
    count: int
    dry_run: bool

    def __str__(self) -> str:
        mode = "DRY RUN — " if self.dry_run else ""
        lines = [
            f"{mode}Bulk label '{self.label}' on {self.repo} (filter: '{self.filter_text}')",
            f"Affected issues: {self.count}",
        ]
        lines.extend(f"  {issue}" for issue in self.affected)
        return "\n".join(lines)


class StaleIssueReport(BaseModel):
    repo: str
    threshold_days: int
    total_stale: int
    by_label: dict[str, int] = {}
    by_assignee: dict[str, int] = {}
    issues: list[IssueSummary] = []

    def __str__(self) -> str:
        lines = [
            f"Stale Issue Report: {self.repo} (>{self.threshold_days}d inactive)",
            f"Total stale: {self.total_stale}",
        ]
        if self.by_label:
            lines.append("\nBy label:")
            lines.extend(f"  {label}: {count}" for label, count in self.by_label.items())
        if self.by_assignee:
            lines.append("\nBy assignee:")
            lines.extend(f"  {user}: {count}" for user, count in self.by_assignee.items())
        if self.issues:
            lines.append("\nIssues:")
            lines.extend(f"  {issue}" for issue in self.issues)
        return "\n".join(lines)


class BulkCloseResult(BaseModel):
    repo: str
    label: str
    older_than_days: int
    closed: list[IssueSummary] = []
    count: int
    dry_run: bool

    def __str__(self) -> str:
        mode = "DRY RUN — " if self.dry_run else ""
        lines = [
            f"{mode}Bulk close '{self.label}' issues older than {self.older_than_days}d in {self.repo}",
            f"Closed: {self.count}",
        ]
        lines.extend(f"  {issue}" for issue in self.closed)
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# PR tool outputs
# ---------------------------------------------------------------------------


class ReviewDashboard(BaseModel):
    repo: str
    total_open: int
    awaiting_review: list[PRSummary] = []
    changes_requested: list[PRSummary] = []
    approved: list[PRSummary] = []

    def __str__(self) -> str:
        lines = [
            f"Review Dashboard: {self.repo}",
            f"Total open PRs: {self.total_open}",
        ]
        if self.awaiting_review:
            lines.append(f"\nAwaiting review ({len(self.awaiting_review)}):")
            lines.extend(f"  {pr}" for pr in self.awaiting_review)
        if self.changes_requested:
            lines.append(f"\nChanges requested ({len(self.changes_requested)}):")
            lines.extend(f"  {pr}" for pr in self.changes_requested)
        if self.approved:
            lines.append(f"\nApproved ({len(self.approved)}):")
            lines.extend(f"  {pr}" for pr in self.approved)
        return "\n".join(lines)


class StalePRReport(BaseModel):
    repo: str
    threshold_days: int
    total_stale: int
    prs: list[PRSummary] = []

    def __str__(self) -> str:
        lines = [
            f"Stale PR Report: {self.repo} (>{self.threshold_days}d inactive)",
            f"Total stale: {self.total_stale}",
        ]
        lines.extend(f"  {pr}" for pr in self.prs)
        return "\n".join(lines)


class CheckStatusOverview(BaseModel):
    repo: str
    total_prs: int
    all_passing: int
    some_failing: int
    some_pending: int
    prs: list[PRCheckSummary] = []

    def __str__(self) -> str:
        lines = [
            f"Check Status Overview: {self.repo}",
            f"Total PRs: {self.total_prs} | Passing: {self.all_passing} | Failing: {self.some_failing} | Pending: {self.some_pending}",
        ]
        lines.extend(str(pr) for pr in self.prs)
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Repo tool outputs
# ---------------------------------------------------------------------------


class HealthScorecard(BaseModel):
    repo: str
    score: int  # 0-100
    checks: list[HealthCheck] = []
    recommendations: list[str] = []

    def __str__(self) -> str:
        lines = [
            f"Health Scorecard: {self.repo} — Score: {self.score}/100",
        ]
        if self.checks:
            lines.append("\nChecks:")
            lines.extend(f"  {check}" for check in self.checks)
        if self.recommendations:
            lines.append("\nRecommendations:")
            lines.extend(f"  - {rec}" for rec in self.recommendations)
        return "\n".join(lines)


class RepoComparison(BaseModel):
    owner: str
    repos: list[HealthScorecard] = []
    inconsistencies: list[str] = []

    def __str__(self) -> str:
        lines = [f"Repo Comparison: {self.owner}"]
        for scorecard in self.repos:
            lines.append(f"  {scorecard.repo}: {scorecard.score}/100")
        if self.inconsistencies:
            lines.append("\nInconsistencies:")
            lines.extend(f"  - {item}" for item in self.inconsistencies)
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Team tool outputs
# ---------------------------------------------------------------------------


class AccessReport(BaseModel):
    target: str
    admins: list[UserPermission] = []
    writers: list[UserPermission] = []
    readers: list[UserPermission] = []
    total_users: int

    def __str__(self) -> str:
        lines = [
            f"Access Report: {self.target}",
            f"Total users: {self.total_users}",
        ]
        if self.admins:
            lines.append(f"\nAdmins ({len(self.admins)}):")
            lines.extend(f"  {u}" for u in self.admins)
        if self.writers:
            lines.append(f"\nWriters ({len(self.writers)}):")
            lines.extend(f"  {u}" for u in self.writers)
        if self.readers:
            lines.append(f"\nReaders ({len(self.readers)}):")
            lines.extend(f"  {u}" for u in self.readers)
        return "\n".join(lines)


class PermissionAuditReport(BaseModel):
    org: str
    total_repos_scanned: int
    findings: list[AuditFinding] = []
    high_count: int
    medium_count: int
    low_count: int

    def __str__(self) -> str:
        lines = [
            f"Permission Audit: {self.org}",
            f"Repos scanned: {self.total_repos_scanned}",
            f"Findings — High: {self.high_count}  Medium: {self.medium_count}  Low: {self.low_count}",
        ]
        if self.findings:
            lines.append("\nFindings:")
            lines.extend(f"  {finding}" for finding in self.findings)
        return "\n".join(lines)
