"""Unit tests for issue tools."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import pytest
import respx

from github_ops_mcp.github_client import GitHubClient
from github_ops_mcp.tools.issues import (
    bulk_label_issues,
    stale_issue_report,
    triage_issues,
)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

RATE_LIMIT_HEADERS = {
    "X-RateLimit-Remaining": "50",
    "X-RateLimit-Reset": "1720100000",
}

NOW = datetime.now(tz=timezone.utc)


def _make_issue(
    number: int,
    title: str,
    labels: list[str] | None = None,
    assignee: str | None = None,
    milestone: str | None = None,
    days_old: int = 5,
    body: str | None = None,
) -> dict:
    """Build a minimal GitHub API issue dict."""
    updated = NOW - timedelta(days=days_old)
    return {
        "number": number,
        "title": title,
        "body": body,
        "html_url": f"https://github.com/owner/repo/issues/{number}",
        "created_at": (NOW - timedelta(days=days_old + 1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "updated_at": updated.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "labels": [{"name": lbl} for lbl in (labels or [])],
        "assignee": {"login": assignee} if assignee else None,
        "milestone": {"title": milestone} if milestone else None,
    }


def _make_pr_item(number: int) -> dict:
    """Build a minimal GitHub API item that looks like a PR (has pull_request key)."""
    return {
        "number": number,
        "title": f"PR #{number}",
        "html_url": f"https://github.com/owner/repo/pull/{number}",
        "created_at": NOW.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "updated_at": NOW.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "labels": [],
        "assignee": None,
        "milestone": None,
        "pull_request": {"url": f"https://api.github.com/repos/owner/repo/pulls/{number}"},
    }


# ---------------------------------------------------------------------------
# triage_issues
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_triage_issues_counts():
    """Three issues: fully untriaged, partially triaged, fully triaged."""
    # Issue 1: no labels, no assignee, no milestone → appears in all three lists
    # Issue 2: has labels, no assignee, has milestone → only missing_assignee
    # Issue 3: has labels, has assignee, has milestone → fully triaged
    issues = [
        _make_issue(1, "Broken login", labels=[], assignee=None, milestone=None),
        _make_issue(2, "Slow query", labels=["bug"], assignee=None, milestone="v1.0"),
        _make_issue(3, "Add dark mode", labels=["enhancement"], assignee="alice", milestone="v1.0"),
    ]

    client = GitHubClient(token="test-token")
    with respx.mock:
        respx.get("https://api.github.com/repos/owner/repo/issues").mock(
            return_value=httpx.Response(200, json=issues, headers=RATE_LIMIT_HEADERS)
        )
        report = await triage_issues(client, "owner", "repo")
    await client.close()

    assert report.repo == "owner/repo"
    # issue 1 and issue 2 are untriaged (2 unique numbers)
    assert report.total_untriaged == 2
    # Only issue 1 and issue 3 (no labels for issue 1; issue 2 has labels)
    assert len(report.missing_labels) == 1
    assert report.missing_labels[0].number == 1
    # issue 1 and issue 2 have no assignee
    assert len(report.missing_assignee) == 2
    assert {i.number for i in report.missing_assignee} == {1, 2}
    # Only issue 1 has no milestone
    assert len(report.missing_milestone) == 1
    assert report.missing_milestone[0].number == 1


@pytest.mark.asyncio
async def test_triage_issues_empty_repo():
    """Empty repo returns zeros."""
    client = GitHubClient(token="test-token")
    with respx.mock:
        respx.get("https://api.github.com/repos/owner/repo/issues").mock(
            return_value=httpx.Response(200, json=[], headers=RATE_LIMIT_HEADERS)
        )
        report = await triage_issues(client, "owner", "repo")
    await client.close()

    assert report.total_untriaged == 0
    assert report.missing_labels == []
    assert report.missing_assignee == []
    assert report.missing_milestone == []


@pytest.mark.asyncio
async def test_triage_issues_skips_prs():
    """PR items mixed in the response must not be counted."""
    items = [
        _make_issue(1, "Real issue", labels=[], assignee=None, milestone=None),
        _make_pr_item(2),
    ]
    client = GitHubClient(token="test-token")
    with respx.mock:
        respx.get("https://api.github.com/repos/owner/repo/issues").mock(
            return_value=httpx.Response(200, json=items, headers=RATE_LIMIT_HEADERS)
        )
        report = await triage_issues(client, "owner", "repo")
    await client.close()

    assert report.total_untriaged == 1
    assert report.missing_labels[0].number == 1


# ---------------------------------------------------------------------------
# stale_issue_report
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stale_issue_report_filters_correctly():
    """Only the issue older than threshold should appear as stale."""
    issues = [
        # 45 days old → stale for threshold=30
        _make_issue(10, "Old bug", labels=["bug"], assignee="bob", days_old=45),
        # 5 days old → NOT stale
        _make_issue(11, "New feature", labels=["enhancement"], assignee="alice", days_old=5),
    ]

    client = GitHubClient(token="test-token")
    with respx.mock:
        respx.get("https://api.github.com/repos/owner/repo/issues").mock(
            return_value=httpx.Response(200, json=issues, headers=RATE_LIMIT_HEADERS)
        )
        report = await stale_issue_report(client, "owner", "repo", days=30)
    await client.close()

    assert report.total_stale == 1
    assert report.issues[0].number == 10
    assert report.by_label == {"bug": 1}
    assert report.by_assignee == {"bob": 1}


@pytest.mark.asyncio
async def test_stale_issue_report_unlabeled_unassigned():
    """Issues with no labels/assignee should go into unlabeled/unassigned buckets."""
    issues = [
        _make_issue(20, "Mystery bug", labels=[], assignee=None, days_old=60),
    ]
    client = GitHubClient(token="test-token")
    with respx.mock:
        respx.get("https://api.github.com/repos/owner/repo/issues").mock(
            return_value=httpx.Response(200, json=issues, headers=RATE_LIMIT_HEADERS)
        )
        report = await stale_issue_report(client, "owner", "repo", days=30)
    await client.close()

    assert report.total_stale == 1
    assert report.by_label == {"unlabeled": 1}
    assert report.by_assignee == {"unassigned": 1}


# ---------------------------------------------------------------------------
# bulk_label_issues (dry run)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bulk_label_dry_run_matches():
    """dry_run=True should match titles containing filter_text, not PATCH anything."""
    issues = [
        _make_issue(30, "fix: login crash", labels=[], assignee=None, milestone=None),
        _make_issue(31, "chore: update deps", labels=[], assignee=None, milestone=None),
        _make_issue(32, "fix: broken redirect", labels=[], assignee=None, milestone=None),
    ]

    client = GitHubClient(token="test-token")
    with respx.mock:
        respx.get("https://api.github.com/repos/owner/repo/issues").mock(
            return_value=httpx.Response(200, json=issues, headers=RATE_LIMIT_HEADERS)
        )
        result = await bulk_label_issues(
            client, "owner", "repo", label="bug", filter_text="fix", dry_run=True
        )
    await client.close()

    assert result.dry_run is True
    assert result.count == 2
    assert {i.number for i in result.affected} == {30, 32}
    assert result.label == "bug"
    assert result.filter_text == "fix"


@pytest.mark.asyncio
async def test_bulk_label_matches_body():
    """filter_text should match against issue body, not just title."""
    issues = [
        _make_issue(50, "Generic title", body="Getting a timeout error on login page"),
        _make_issue(51, "Another issue", body="Everything works fine"),
    ]

    client = GitHubClient(token="test-token")
    with respx.mock:
        respx.get("https://api.github.com/repos/owner/repo/issues").mock(
            return_value=httpx.Response(200, json=issues, headers=RATE_LIMIT_HEADERS)
        )
        result = await bulk_label_issues(
            client, "owner", "repo", label="bug/perf", filter_text="timeout", dry_run=True
        )
    await client.close()

    assert result.count == 1
    assert result.affected[0].number == 50


@pytest.mark.asyncio
async def test_bulk_label_dry_run_no_match():
    """No matching issues → count is 0."""
    issues = [
        _make_issue(40, "chore: cleanup", labels=[], assignee=None, milestone=None),
    ]

    client = GitHubClient(token="test-token")
    with respx.mock:
        respx.get("https://api.github.com/repos/owner/repo/issues").mock(
            return_value=httpx.Response(200, json=issues, headers=RATE_LIMIT_HEADERS)
        )
        result = await bulk_label_issues(
            client, "owner", "repo", label="bug", filter_text="crash", dry_run=True
        )
    await client.close()

    assert result.count == 0
    assert result.affected == []
