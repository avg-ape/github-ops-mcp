"""Pull request tools for github-ops-mcp."""

from __future__ import annotations

from datetime import datetime, timezone

from github_ops_mcp.github_client import GitHubClient
from github_ops_mcp.models import (
    CheckResult,
    CheckStatusOverview,
    PRCheckSummary,
    PRSummary,
    ReviewDashboard,
    StalePRReport,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _determine_review_status(
    reviews: list[dict],
    requested_reviewers: list[dict],
) -> tuple[str, list[str]]:
    """Determine the review status and reviewers for a PR.

    Returns a (status, reviewer_logins) tuple.
    """
    if not reviews and requested_reviewers:
        reviewers = [r["login"] for r in requested_reviewers]
        return ("awaiting_review", reviewers)

    # Track latest state per reviewer (only APPROVED / CHANGES_REQUESTED matter)
    latest: dict[str, str] = {}
    for review in reviews:
        login = review["user"]["login"]
        state = review["state"]
        if state in ("APPROVED", "CHANGES_REQUESTED"):
            latest[login] = state

    # Merge in any still-pending requested reviewers who haven't reviewed yet
    pending_logins = [r["login"] for r in requested_reviewers if r["login"] not in latest]
    all_reviewers = list(latest.keys()) + pending_logins

    states = set(latest.values())
    if "CHANGES_REQUESTED" in states:
        return ("changes_requested", all_reviewers)
    if "APPROVED" in states:
        return ("approved", all_reviewers)
    return ("awaiting_review", all_reviewers)


def _parse_pr(raw: dict, review_status: str, reviewers: list[str]) -> PRSummary:
    """Convert GitHub API PR JSON to PRSummary."""
    updated_at = datetime.fromisoformat(raw["updated_at"].replace("Z", "+00:00"))
    now = datetime.now(tz=timezone.utc)
    return PRSummary(
        number=raw["number"],
        title=raw["title"],
        url=raw["html_url"],
        author=raw["user"]["login"],
        created_at=datetime.fromisoformat(raw["created_at"].replace("Z", "+00:00")),
        updated_at=updated_at,
        review_status=review_status,
        reviewers=reviewers,
        days_waiting=(now - updated_at).days,
    )


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


async def pr_review_dashboard(
    client: GitHubClient,
    owner: str,
    repo: str,
) -> ReviewDashboard:
    """Return a dashboard of open PRs grouped by review status."""
    raw_prs = await client.get_all(
        f"/repos/{owner}/{repo}/pulls",
        params={"state": "open", "per_page": 100},
    )

    awaiting: list[PRSummary] = []
    changes: list[PRSummary] = []
    approved: list[PRSummary] = []

    for raw in raw_prs:
        reviews = await client.get(f"/repos/{owner}/{repo}/pulls/{raw['number']}/reviews")
        if not isinstance(reviews, list):
            reviews = []
        requested_reviewers = raw.get("requested_reviewers", [])
        status, reviewers = _determine_review_status(reviews, requested_reviewers)
        pr = _parse_pr(raw, status, reviewers)

        if status == "awaiting_review":
            awaiting.append(pr)
        elif status == "changes_requested":
            changes.append(pr)
        elif status == "approved":
            approved.append(pr)

    # Sort each group by days_waiting descending
    awaiting.sort(key=lambda p: p.days_waiting, reverse=True)
    changes.sort(key=lambda p: p.days_waiting, reverse=True)
    approved.sort(key=lambda p: p.days_waiting, reverse=True)

    return ReviewDashboard(
        repo=f"{owner}/{repo}",
        total_open=len(raw_prs),
        awaiting_review=awaiting,
        changes_requested=changes,
        approved=approved,
    )


async def stale_pr_report(
    client: GitHubClient,
    owner: str,
    repo: str,
    days: int = 14,
) -> StalePRReport:
    """Return a report of open PRs that have not been updated in ``days`` days."""
    raw_prs = await client.get_all(
        f"/repos/{owner}/{repo}/pulls",
        params={"state": "open", "per_page": 100},
    )

    now = datetime.now(tz=timezone.utc)
    stale: list[PRSummary] = []

    for raw in raw_prs:
        updated_at = datetime.fromisoformat(raw["updated_at"].replace("Z", "+00:00"))
        if (now - updated_at).days < days:
            continue

        reviews = await client.get(f"/repos/{owner}/{repo}/pulls/{raw['number']}/reviews")
        if not isinstance(reviews, list):
            reviews = []
        requested_reviewers = raw.get("requested_reviewers", [])
        status, reviewers = _determine_review_status(reviews, requested_reviewers)
        pr = _parse_pr(raw, status, reviewers)
        stale.append(pr)

    return StalePRReport(
        repo=f"{owner}/{repo}",
        threshold_days=days,
        total_stale=len(stale),
        prs=stale,
    )


async def pr_check_status(
    client: GitHubClient,
    owner: str,
    repo: str,
) -> CheckStatusOverview:
    """Return a check-run status overview for all open PRs."""
    raw_prs = await client.get_all(
        f"/repos/{owner}/{repo}/pulls",
        params={"state": "open", "per_page": 100},
    )

    pr_summaries: list[PRCheckSummary] = []
    all_passing_count = 0
    some_failing_count = 0
    some_pending_count = 0

    for raw in raw_prs:
        sha = raw["head"]["sha"]
        check_data = await client.get(f"/repos/{owner}/{repo}/commits/{sha}/check-runs")
        if isinstance(check_data, dict):
            run_list = check_data.get("check_runs", [])
        else:
            run_list = []

        checks: list[CheckResult] = []
        passing = 0
        failing = 0
        pending = 0

        for run in run_list:
            status_str = run.get("status", "")
            conclusion = run.get("conclusion")

            if status_str != "completed":
                mapped = "pending"
            elif conclusion in ("failure", "cancelled", "timed_out"):
                mapped = "failure"
            elif conclusion == "success":
                mapped = "success"
            elif conclusion == "neutral":
                mapped = "neutral"
            else:
                mapped = "pending"

            checks.append(CheckResult(name=run["name"], status=mapped, url=run.get("html_url")))

            if mapped == "success" or mapped == "neutral":
                passing += 1
            elif mapped == "failure":
                failing += 1
            else:
                pending += 1

        pr_summaries.append(
            PRCheckSummary(
                number=raw["number"],
                title=raw["title"],
                checks=checks,
                passing=passing,
                failing=failing,
                pending=pending,
            )
        )

        if failing > 0:
            some_failing_count += 1
        elif pending > 0:
            some_pending_count += 1
        else:
            all_passing_count += 1

    return CheckStatusOverview(
        repo=f"{owner}/{repo}",
        total_prs=len(raw_prs),
        all_passing=all_passing_count,
        some_failing=some_failing_count,
        some_pending=some_pending_count,
        prs=pr_summaries,
    )
