"""Issue management tools for github-ops-mcp."""

from __future__ import annotations

from datetime import datetime, timezone

from github_ops_mcp.github_client import GitHubClient
from github_ops_mcp.models import (
    BulkCloseResult,
    BulkLabelResult,
    IssueSummary,
    StaleIssueReport,
    TriageReport,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_issue(raw: dict) -> IssueSummary:
    """Convert GitHub API issue JSON to IssueSummary."""
    return IssueSummary(
        number=raw["number"],
        title=raw["title"],
        url=raw["html_url"],
        created_at=datetime.fromisoformat(raw["created_at"].replace("Z", "+00:00")),
        updated_at=datetime.fromisoformat(raw["updated_at"].replace("Z", "+00:00")),
        labels=[label["name"] for label in raw.get("labels", [])],
        assignee=raw["assignee"]["login"] if raw.get("assignee") else None,
        milestone=raw["milestone"]["title"] if raw.get("milestone") else None,
    )


def _is_issue(raw: dict) -> bool:
    """Return True if the item is a real issue (not a PR).

    GitHub's issues list endpoint includes PRs — filter them out by checking
    for the ``pull_request`` key.
    """
    pr_field = raw.get("pull_request")
    return pr_field is None


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


async def triage_issues(
    client: GitHubClient,
    owner: str,
    repo: str,
    since: str | None = None,
) -> TriageReport:
    """Return a triage report for open issues missing labels, assignee, or milestone."""
    params: dict = {"state": "open", "per_page": 100}
    if since:
        params["since"] = since

    raw_items = await client.get_all(f"/repos/{owner}/{repo}/issues", params=params)
    issues = [_parse_issue(r) for r in raw_items if _is_issue(r)]

    missing_labels = [i for i in issues if not i.labels]
    missing_assignee = [i for i in issues if not i.assignee]
    missing_milestone = [i for i in issues if not i.milestone]

    # Count unique issue numbers across all three lists
    untriaged_numbers = {i.number for i in missing_labels}
    untriaged_numbers |= {i.number for i in missing_assignee}
    untriaged_numbers |= {i.number for i in missing_milestone}

    return TriageReport(
        repo=f"{owner}/{repo}",
        total_untriaged=len(untriaged_numbers),
        missing_labels=missing_labels,
        missing_assignee=missing_assignee,
        missing_milestone=missing_milestone,
    )


async def stale_issue_report(
    client: GitHubClient,
    owner: str,
    repo: str,
    days: int = 30,
) -> StaleIssueReport:
    """Return a report of open issues that have not been updated in ``days`` days."""
    raw_items = await client.get_all(
        f"/repos/{owner}/{repo}/issues",
        params={"state": "open", "per_page": 100},
    )
    now = datetime.now(tz=timezone.utc)
    stale: list[IssueSummary] = []

    for r in raw_items:
        if not _is_issue(r):
            continue
        issue = _parse_issue(r)
        if (now - issue.updated_at).days >= days:
            stale.append(issue)

    by_label: dict[str, int] = {}
    by_assignee: dict[str, int] = {}

    for issue in stale:
        if issue.labels:
            for label in issue.labels:
                by_label[label] = by_label.get(label, 0) + 1
        else:
            by_label["unlabeled"] = by_label.get("unlabeled", 0) + 1

        key = issue.assignee if issue.assignee else "unassigned"
        by_assignee[key] = by_assignee.get(key, 0) + 1

    return StaleIssueReport(
        repo=f"{owner}/{repo}",
        threshold_days=days,
        total_stale=len(stale),
        by_label=by_label,
        by_assignee=by_assignee,
        issues=stale,
    )


async def bulk_label_issues(
    client: GitHubClient,
    owner: str,
    repo: str,
    label: str,
    filter_text: str,
    dry_run: bool = True,
) -> BulkLabelResult:
    """Apply ``label`` to all open issues whose title contains ``filter_text``."""
    raw_items = await client.get_all(
        f"/repos/{owner}/{repo}/issues",
        params={"state": "open", "per_page": 100},
    )

    matched: list[IssueSummary] = []
    filter_lower = filter_text.lower()

    for r in raw_items:
        if not _is_issue(r):
            continue
        if filter_lower not in r["title"].lower():
            continue
        issue = _parse_issue(r)
        matched.append(issue)

        if not dry_run:
            existing = [lbl["name"] for lbl in r.get("labels", [])]
            if label not in existing:
                new_labels = existing + [label]
                await client.patch(
                    f"/repos/{owner}/{repo}/issues/{issue.number}",
                    json={"labels": new_labels},
                )

    return BulkLabelResult(
        repo=f"{owner}/{repo}",
        label=label,
        filter_text=filter_text,
        affected=matched,
        count=len(matched),
        dry_run=dry_run,
    )


async def close_resolved_issues(
    client: GitHubClient,
    owner: str,
    repo: str,
    label: str,
    older_than_days: int,
    comment: str = "Closing — resolved and inactive.",
    dry_run: bool = True,
) -> BulkCloseResult:
    """Close open issues tagged with ``label`` that haven't been updated in ``older_than_days`` days."""
    raw_items = await client.get_all(
        f"/repos/{owner}/{repo}/issues",
        params={"state": "open", "labels": label, "per_page": 100},
    )

    now = datetime.now(tz=timezone.utc)
    to_close: list[IssueSummary] = []

    for r in raw_items:
        if not _is_issue(r):
            continue
        issue = _parse_issue(r)
        if (now - issue.updated_at).days >= older_than_days:
            to_close.append(issue)

            if not dry_run:
                await client.post(
                    f"/repos/{owner}/{repo}/issues/{issue.number}/comments",
                    json={"body": comment},
                )
                await client.patch(
                    f"/repos/{owner}/{repo}/issues/{issue.number}",
                    json={"state": "closed"},
                )

    return BulkCloseResult(
        repo=f"{owner}/{repo}",
        label=label,
        older_than_days=older_than_days,
        closed=to_close,
        count=len(to_close),
        dry_run=dry_run,
    )
