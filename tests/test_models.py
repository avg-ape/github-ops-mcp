"""Smoke tests for github_ops_mcp models."""

from datetime import datetime, timezone

import pytest

from github_ops_mcp.models import (
    AccessReport,
    AuditFinding,
    BulkCloseResult,
    BulkLabelResult,
    CheckResult,
    CheckStatusOverview,
    HealthCheck,
    HealthScorecard,
    IssueSummary,
    PermissionAuditReport,
    PRCheckSummary,
    PRSummary,
    RepoComparison,
    ReviewDashboard,
    StalePRReport,
    StaleIssueReport,
    TriageReport,
    UserPermission,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 7, 4, 12, 0, 0, tzinfo=timezone.utc)


def make_issue(number: int = 42, title: str = "Fix login bug", assignee: str | None = "alice") -> IssueSummary:
    return IssueSummary(
        number=number,
        title=title,
        url=f"https://github.com/org/repo/issues/{number}",
        created_at=_NOW,
        updated_at=_NOW,
        labels=["bug", "perf"],
        assignee=assignee,
        milestone="v1.0",
    )


def make_pr(number: int = 10, title: str = "Add feature") -> PRSummary:
    return PRSummary(
        number=number,
        title=title,
        url=f"https://github.com/org/repo/pulls/{number}",
        author="alice",
        created_at=_NOW,
        updated_at=_NOW,
        review_status="approved",
        reviewers=["bob"],
        days_waiting=3,
    )


def make_health_check(passed: bool = True) -> HealthCheck:
    return HealthCheck(
        name="Branch protection",
        passed=passed,
        detail="Enabled on main",
    )


# ---------------------------------------------------------------------------
# IssueSummary
# ---------------------------------------------------------------------------


def test_issue_summary_str_includes_number():
    issue = make_issue()
    assert "#42" in str(issue)


def test_issue_summary_str_includes_title():
    issue = make_issue()
    assert "Fix login bug" in str(issue)


def test_issue_summary_str_includes_assignee():
    issue = make_issue()
    assert "alice" in str(issue)


def test_issue_summary_str_no_assignee():
    issue = make_issue(assignee=None)
    result = str(issue)
    assert "#42" in result
    assert "assignee" not in result


def test_issue_summary_str_includes_labels():
    issue = make_issue()
    result = str(issue)
    assert "bug" in result
    assert "perf" in result


def test_issue_summary_serialization():
    issue = make_issue()
    data = issue.model_dump()
    assert data["number"] == 42
    assert data["title"] == "Fix login bug"
    assert data["assignee"] == "alice"
    assert data["labels"] == ["bug", "perf"]


# ---------------------------------------------------------------------------
# HealthCheck
# ---------------------------------------------------------------------------


def test_health_check_pass_str():
    hc = make_health_check(passed=True)
    result = str(hc)
    assert "[PASS]" in result
    assert "Branch protection" in result


def test_health_check_fail_str():
    hc = make_health_check(passed=False)
    result = str(hc)
    assert "[FAIL]" in result


def test_health_check_serialization():
    hc = make_health_check()
    data = hc.model_dump()
    assert data["passed"] is True
    assert data["name"] == "Branch protection"


# ---------------------------------------------------------------------------
# TriageReport
# ---------------------------------------------------------------------------


def test_triage_report_str_includes_count():
    issue = make_issue()
    report = TriageReport(
        repo="org/repo",
        total_untriaged=5,
        missing_labels=[issue],
        missing_assignee=[],
        missing_milestone=[],
    )
    result = str(report)
    assert "5" in result
    assert "org/repo" in result


def test_triage_report_str_includes_missing_labels_section():
    issue = make_issue()
    report = TriageReport(
        repo="org/repo",
        total_untriaged=1,
        missing_labels=[issue],
        missing_assignee=[],
        missing_milestone=[],
    )
    result = str(report)
    assert "Missing labels" in result


def test_triage_report_str_missing_assignee_section():
    issue = make_issue()
    report = TriageReport(
        repo="org/repo",
        total_untriaged=1,
        missing_labels=[],
        missing_assignee=[issue],
        missing_milestone=[],
    )
    result = str(report)
    assert "Missing assignee" in result


def test_triage_report_str_missing_milestone_section():
    issue = make_issue()
    report = TriageReport(
        repo="org/repo",
        total_untriaged=1,
        missing_labels=[],
        missing_assignee=[],
        missing_milestone=[issue],
    )
    result = str(report)
    assert "Missing milestone" in result


def test_triage_report_serialization():
    report = TriageReport(
        repo="org/repo",
        total_untriaged=0,
        missing_labels=[],
        missing_assignee=[],
        missing_milestone=[],
    )
    data = report.model_dump()
    assert data["repo"] == "org/repo"
    assert data["total_untriaged"] == 0


# ---------------------------------------------------------------------------
# PRSummary
# ---------------------------------------------------------------------------


def test_pr_summary_str():
    pr = make_pr()
    result = str(pr)
    assert "#10" in result
    assert "Add feature" in result
    assert "alice" in result
    assert "approved" in result
    assert "3d waiting" in result
    assert "bob" in result


# ---------------------------------------------------------------------------
# UserPermission
# ---------------------------------------------------------------------------


def test_user_permission_str():
    up = UserPermission(login="alice", permission="admin", source="team:core")
    result = str(up)
    assert "alice" in result
    assert "admin" in result
    assert "team:core" in result


# ---------------------------------------------------------------------------
# CheckResult
# ---------------------------------------------------------------------------


def test_check_result_str():
    cr = CheckResult(name="tests", status="success", url=None)
    result = str(cr)
    assert "SUCCESS" in result
    assert "tests" in result


# ---------------------------------------------------------------------------
# PRCheckSummary
# ---------------------------------------------------------------------------


def test_pr_check_summary_str():
    check = CheckResult(name="ci", status="success")
    summary = PRCheckSummary(
        number=5,
        title="My PR",
        checks=[check],
        passing=1,
        failing=0,
        pending=0,
    )
    result = str(summary)
    assert "#5" in result
    assert "My PR" in result


# ---------------------------------------------------------------------------
# AuditFinding
# ---------------------------------------------------------------------------


def test_audit_finding_str():
    finding = AuditFinding(
        repo="org/repo",
        finding="Admin access without MFA",
        severity="high",
        users=["alice"],
    )
    result = str(finding)
    assert "HIGH" in result
    assert "org/repo" in result
    assert "alice" in result


# ---------------------------------------------------------------------------
# HealthScorecard
# ---------------------------------------------------------------------------


def test_health_scorecard_str():
    hc = make_health_check()
    card = HealthScorecard(
        repo="org/repo",
        score=85,
        checks=[hc],
        recommendations=["Enable Dependabot"],
    )
    result = str(card)
    assert "85" in result
    assert "org/repo" in result
    assert "Enable Dependabot" in result


def test_health_scorecard_serialization():
    card = HealthScorecard(repo="org/repo", score=100, checks=[], recommendations=[])
    data = card.model_dump()
    assert data["score"] == 100


# ---------------------------------------------------------------------------
# RepoComparison
# ---------------------------------------------------------------------------


def test_repo_comparison_str():
    card = HealthScorecard(repo="org/repo", score=75, checks=[], recommendations=[])
    comp = RepoComparison(
        owner="org",
        repos=[card],
        inconsistencies=["Branch protection missing on org/repo"],
    )
    result = str(comp)
    assert "org" in result
    assert "75" in result
    assert "Branch protection missing" in result


# ---------------------------------------------------------------------------
# ReviewDashboard
# ---------------------------------------------------------------------------


def test_review_dashboard_str():
    pr = make_pr()
    dash = ReviewDashboard(
        repo="org/repo",
        total_open=3,
        awaiting_review=[pr],
        changes_requested=[],
        approved=[],
    )
    result = str(dash)
    assert "org/repo" in result
    assert "Awaiting review" in result


# ---------------------------------------------------------------------------
# StalePRReport
# ---------------------------------------------------------------------------


def test_stale_pr_report_str():
    pr = make_pr()
    report = StalePRReport(
        repo="org/repo",
        threshold_days=14,
        total_stale=1,
        prs=[pr],
    )
    result = str(report)
    assert "14" in result
    assert "org/repo" in result


# ---------------------------------------------------------------------------
# CheckStatusOverview
# ---------------------------------------------------------------------------


def test_check_status_overview_str():
    overview = CheckStatusOverview(
        repo="org/repo",
        total_prs=10,
        all_passing=8,
        some_failing=1,
        some_pending=1,
        prs=[],
    )
    result = str(overview)
    assert "org/repo" in result
    assert "10" in result


# ---------------------------------------------------------------------------
# BulkLabelResult
# ---------------------------------------------------------------------------


def test_bulk_label_result_str():
    issue = make_issue()
    result_obj = BulkLabelResult(
        repo="org/repo",
        label="needs-triage",
        filter_text="login",
        affected=[issue],
        count=1,
        dry_run=True,
    )
    result = str(result_obj)
    assert "DRY RUN" in result
    assert "needs-triage" in result


# ---------------------------------------------------------------------------
# StaleIssueReport
# ---------------------------------------------------------------------------


def test_stale_issue_report_str():
    issue = make_issue()
    report = StaleIssueReport(
        repo="org/repo",
        threshold_days=30,
        total_stale=1,
        by_label={"bug": 1},
        by_assignee={"alice": 1},
        issues=[issue],
    )
    result = str(report)
    assert "30" in result
    assert "bug" in result


# ---------------------------------------------------------------------------
# BulkCloseResult
# ---------------------------------------------------------------------------


def test_bulk_close_result_str():
    issue = make_issue()
    result_obj = BulkCloseResult(
        repo="org/repo",
        label="wontfix",
        older_than_days=90,
        closed=[issue],
        count=1,
        dry_run=False,
    )
    result = str(result_obj)
    assert "wontfix" in result
    assert "90" in result
    assert "DRY RUN" not in result


# ---------------------------------------------------------------------------
# AccessReport
# ---------------------------------------------------------------------------


def test_access_report_str():
    up = UserPermission(login="alice", permission="admin", source="team:core")
    report = AccessReport(
        target="org/repo",
        admins=[up],
        writers=[],
        readers=[],
        total_users=1,
    )
    result = str(report)
    assert "org/repo" in result
    assert "Admins" in result
    assert "alice" in result


# ---------------------------------------------------------------------------
# PermissionAuditReport
# ---------------------------------------------------------------------------


def test_permission_audit_report_str():
    finding = AuditFinding(
        repo="org/repo",
        finding="Public repo with admin team",
        severity="high",
        users=[],
    )
    report = PermissionAuditReport(
        org="myorg",
        total_repos_scanned=20,
        findings=[finding],
        high_count=1,
        medium_count=0,
        low_count=0,
    )
    result = str(report)
    assert "myorg" in result
    assert "20" in result
    assert "HIGH" in result
