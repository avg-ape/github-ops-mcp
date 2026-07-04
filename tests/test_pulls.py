"""Unit tests for pull request tools."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import pytest
import respx

from github_ops_mcp.github_client import GitHubClient
from github_ops_mcp.tools.pulls import pr_check_status, pr_review_dashboard, stale_pr_report

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

RATE_LIMIT_HEADERS = {
    "X-RateLimit-Remaining": "50",
    "X-RateLimit-Reset": "1720100000",
}

NOW = datetime.now(tz=timezone.utc)


def _make_pr(
    number: int,
    title: str,
    sha: str = "abc123",
    days_old: int = 2,
    requested_reviewers: list[str] | None = None,
    author: str = "dev",
) -> dict:
    """Build a minimal GitHub API pull request dict."""
    updated = NOW - timedelta(days=days_old)
    return {
        "number": number,
        "title": title,
        "html_url": f"https://github.com/owner/repo/pull/{number}",
        "user": {"login": author},
        "created_at": (NOW - timedelta(days=days_old + 1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "updated_at": updated.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "requested_reviewers": [{"login": r} for r in (requested_reviewers or [])],
        "head": {"sha": sha},
    }


def _make_review(login: str, state: str) -> dict:
    """Build a minimal GitHub API review dict."""
    return {"user": {"login": login}, "state": state}


def _make_check_run(name: str, status: str, conclusion: str | None, url: str = "https://ci.example.com") -> dict:
    """Build a minimal GitHub API check-run dict."""
    return {
        "name": name,
        "status": status,
        "conclusion": conclusion,
        "html_url": url,
    }


# ---------------------------------------------------------------------------
# pr_review_dashboard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pr_review_dashboard_groups_correctly():
    """Two PRs: one changes_requested, one approved — verify grouping."""
    pr1 = _make_pr(1, "Refactor auth", sha="sha1", requested_reviewers=["alice"])
    pr2 = _make_pr(2, "Add caching", sha="sha2", requested_reviewers=["bob"])

    reviews_pr1 = [_make_review("alice", "CHANGES_REQUESTED")]
    reviews_pr2 = [_make_review("bob", "APPROVED")]

    client = GitHubClient(token="test-token")
    with respx.mock:
        respx.get("https://api.github.com/repos/owner/repo/pulls").mock(
            return_value=httpx.Response(200, json=[pr1, pr2], headers=RATE_LIMIT_HEADERS)
        )
        respx.get("https://api.github.com/repos/owner/repo/pulls/1/reviews").mock(
            return_value=httpx.Response(200, json=reviews_pr1, headers=RATE_LIMIT_HEADERS)
        )
        respx.get("https://api.github.com/repos/owner/repo/pulls/2/reviews").mock(
            return_value=httpx.Response(200, json=reviews_pr2, headers=RATE_LIMIT_HEADERS)
        )
        dashboard = await pr_review_dashboard(client, "owner", "repo")
    await client.close()

    assert dashboard.total_open == 2
    assert len(dashboard.changes_requested) == 1
    assert dashboard.changes_requested[0].number == 1
    assert len(dashboard.approved) == 1
    assert dashboard.approved[0].number == 2
    assert dashboard.awaiting_review == []


@pytest.mark.asyncio
async def test_pr_review_dashboard_awaiting_review():
    """PR with no reviews but requested_reviewers → awaiting_review."""
    pr = _make_pr(5, "New feature", sha="sha5", requested_reviewers=["carol"])

    client = GitHubClient(token="test-token")
    with respx.mock:
        respx.get("https://api.github.com/repos/owner/repo/pulls").mock(
            return_value=httpx.Response(200, json=[pr], headers=RATE_LIMIT_HEADERS)
        )
        respx.get("https://api.github.com/repos/owner/repo/pulls/5/reviews").mock(
            return_value=httpx.Response(200, json=[], headers=RATE_LIMIT_HEADERS)
        )
        dashboard = await pr_review_dashboard(client, "owner", "repo")
    await client.close()

    assert len(dashboard.awaiting_review) == 1
    assert dashboard.awaiting_review[0].number == 5
    assert "carol" in dashboard.awaiting_review[0].reviewers


# ---------------------------------------------------------------------------
# stale_pr_report
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stale_pr_report_filters_correctly():
    """Old PR appears in stale list; recent PR does not."""
    old_pr = _make_pr(10, "Legacy refactor", sha="sha10", days_old=20)
    recent_pr = _make_pr(11, "Quick fix", sha="sha11", days_old=3)

    client = GitHubClient(token="test-token")
    with respx.mock:
        respx.get("https://api.github.com/repos/owner/repo/pulls").mock(
            return_value=httpx.Response(200, json=[old_pr, recent_pr], headers=RATE_LIMIT_HEADERS)
        )
        # Only the stale PR fetches reviews
        respx.get("https://api.github.com/repos/owner/repo/pulls/10/reviews").mock(
            return_value=httpx.Response(200, json=[], headers=RATE_LIMIT_HEADERS)
        )
        report = await stale_pr_report(client, "owner", "repo", days=14)
    await client.close()

    assert report.total_stale == 1
    assert report.prs[0].number == 10
    assert report.threshold_days == 14


# ---------------------------------------------------------------------------
# pr_check_status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pr_check_status_passing_and_failing():
    """PR with one passing and one failing check → some_failing count incremented."""
    pr = _make_pr(20, "Feature branch", sha="deadbeef")

    check_runs_response = {
        "total_count": 2,
        "check_runs": [
            _make_check_run("Unit tests", "completed", "success"),
            _make_check_run("Lint", "completed", "failure"),
        ],
    }

    client = GitHubClient(token="test-token")
    with respx.mock:
        respx.get("https://api.github.com/repos/owner/repo/pulls").mock(
            return_value=httpx.Response(200, json=[pr], headers=RATE_LIMIT_HEADERS)
        )
        respx.get("https://api.github.com/repos/owner/repo/commits/deadbeef/check-runs").mock(
            return_value=httpx.Response(200, json=check_runs_response, headers=RATE_LIMIT_HEADERS)
        )
        overview = await pr_check_status(client, "owner", "repo")
    await client.close()

    assert overview.total_prs == 1
    assert overview.some_failing == 1
    assert overview.all_passing == 0
    assert overview.some_pending == 0

    pr_summary = overview.prs[0]
    assert pr_summary.number == 20
    assert pr_summary.passing == 1
    assert pr_summary.failing == 1
    assert pr_summary.pending == 0

    statuses = {c.name: c.status for c in pr_summary.checks}
    assert statuses["Unit tests"] == "success"
    assert statuses["Lint"] == "failure"


@pytest.mark.asyncio
async def test_pr_check_status_all_passing():
    """PR with only successful checks → all_passing incremented."""
    pr = _make_pr(21, "Docs update", sha="cafebabe")

    check_runs_response = {
        "total_count": 1,
        "check_runs": [
            _make_check_run("CI", "completed", "success"),
        ],
    }

    client = GitHubClient(token="test-token")
    with respx.mock:
        respx.get("https://api.github.com/repos/owner/repo/pulls").mock(
            return_value=httpx.Response(200, json=[pr], headers=RATE_LIMIT_HEADERS)
        )
        respx.get("https://api.github.com/repos/owner/repo/commits/cafebabe/check-runs").mock(
            return_value=httpx.Response(200, json=check_runs_response, headers=RATE_LIMIT_HEADERS)
        )
        overview = await pr_check_status(client, "owner", "repo")
    await client.close()

    assert overview.all_passing == 1
    assert overview.some_failing == 0
    assert overview.some_pending == 0


@pytest.mark.asyncio
async def test_pr_check_status_pending():
    """Check that is not completed maps to pending status."""
    pr = _make_pr(22, "In-progress feature", sha="beefdead")

    check_runs_response = {
        "total_count": 1,
        "check_runs": [
            _make_check_run("CI", "in_progress", None),
        ],
    }

    client = GitHubClient(token="test-token")
    with respx.mock:
        respx.get("https://api.github.com/repos/owner/repo/pulls").mock(
            return_value=httpx.Response(200, json=[pr], headers=RATE_LIMIT_HEADERS)
        )
        respx.get("https://api.github.com/repos/owner/repo/commits/beefdead/check-runs").mock(
            return_value=httpx.Response(200, json=check_runs_response, headers=RATE_LIMIT_HEADERS)
        )
        overview = await pr_check_status(client, "owner", "repo")
    await client.close()

    assert overview.some_pending == 1
    pr_summary = overview.prs[0]
    assert pr_summary.checks[0].status == "pending"
