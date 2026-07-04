from mcp.server.fastmcp import FastMCP

from github_ops_mcp.github_client import GitHubClient, GitHubAPIError
from github_ops_mcp.tools import issues, pulls, repos, teams

mcp = FastMCP("github-ops")


def _error(message: str) -> str:
    return f"Error: {message}"


@mcp.tool()
async def triage_issues(owner: str, repo: str, since: str | None = None) -> str:
    """Find issues missing labels, assignees, or milestones. Use this to identify untriaged work."""
    client = GitHubClient()
    try:
        report = await issues.triage_issues(client, owner, repo, since)
        return str(report)
    except GitHubAPIError as e:
        return _error(e.message)
    finally:
        await client.close()


@mcp.tool()
async def bulk_label_issues(owner: str, repo: str, label: str, filter_text: str, dry_run: bool = True) -> str:
    """Apply a label to all issues matching a text filter. Defaults to dry-run mode."""
    client = GitHubClient()
    try:
        result = await issues.bulk_label_issues(client, owner, repo, label, filter_text, dry_run)
        return str(result)
    except GitHubAPIError as e:
        return _error(e.message)
    finally:
        await client.close()


@mcp.tool()
async def stale_issue_report(owner: str, repo: str, days: int = 30) -> str:
    """Find issues with no activity in N days, grouped by label and assignee."""
    client = GitHubClient()
    try:
        report = await issues.stale_issue_report(client, owner, repo, days)
        return str(report)
    except GitHubAPIError as e:
        return _error(e.message)
    finally:
        await client.close()


@mcp.tool()
async def close_resolved_issues(owner: str, repo: str, label: str, older_than_days: int, comment: str = "Closing — resolved and inactive.", dry_run: bool = True) -> str:
    """Bulk-close issues with a specific label that are older than N days. Defaults to dry-run mode."""
    client = GitHubClient()
    try:
        result = await issues.close_resolved_issues(client, owner, repo, label, older_than_days, comment, dry_run)
        return str(result)
    except GitHubAPIError as e:
        return _error(e.message)
    finally:
        await client.close()


@mcp.tool()
async def pr_review_dashboard(owner: str, repo: str) -> str:
    """Show open PRs grouped by review status (awaiting, changes requested, approved) with wait times."""
    client = GitHubClient()
    try:
        dashboard = await pulls.pr_review_dashboard(client, owner, repo)
        return str(dashboard)
    except GitHubAPIError as e:
        return _error(e.message)
    finally:
        await client.close()


@mcp.tool()
async def stale_pr_report(owner: str, repo: str, days: int = 14) -> str:
    """Find pull requests with no activity in N days."""
    client = GitHubClient()
    try:
        report = await pulls.stale_pr_report(client, owner, repo, days)
        return str(report)
    except GitHubAPIError as e:
        return _error(e.message)
    finally:
        await client.close()


@mcp.tool()
async def pr_check_status(owner: str, repo: str) -> str:
    """Aggregate CI/check status across all open PRs — quick 'is anything red' overview."""
    client = GitHubClient()
    try:
        overview = await pulls.pr_check_status(client, owner, repo)
        return str(overview)
    except GitHubAPIError as e:
        return _error(e.message)
    finally:
        await client.close()


@mcp.tool()
async def repo_health_audit(owner: str, repo: str) -> str:
    """Audit a repo for operational hygiene: branch protection, CODEOWNERS, CI, license, security policy."""
    client = GitHubClient()
    try:
        scorecard = await repos.repo_health_audit(client, owner, repo)
        return str(scorecard)
    except GitHubAPIError as e:
        return _error(e.message)
    finally:
        await client.close()


@mcp.tool()
async def repo_compare(owner: str, repos_list: list[str]) -> str:
    """Compare health audit results across multiple repos to find inconsistencies."""
    client = GitHubClient()
    try:
        comparison = await repos.repo_compare(client, owner, repos_list)
        return str(comparison)
    except GitHubAPIError as e:
        return _error(e.message)
    finally:
        await client.close()


@mcp.tool()
async def team_access_review(owner: str, repo: str | None = None, team: str | None = None) -> str:
    """List users and their permission levels for a repo or org. Shows who has admin, write, or read access."""
    client = GitHubClient()
    try:
        report = await teams.team_access_review(client, owner, repo, team)
        return str(report)
    except GitHubAPIError as e:
        return _error(e.message)
    finally:
        await client.close()


@mcp.tool()
async def permission_audit(owner: str) -> str:
    """Audit an org for permission issues: outside collaborators, direct access bypassing teams."""
    client = GitHubClient()
    try:
        report = await teams.permission_audit(client, owner)
        return str(report)
    except GitHubAPIError as e:
        return _error(e.message)
    finally:
        await client.close()


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
