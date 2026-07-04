"""Team access and permission audit tools for github-ops-mcp."""

from __future__ import annotations

from github_ops_mcp.github_client import GitHubAPIError, GitHubClient
from github_ops_mcp.models import AccessReport, AuditFinding, PermissionAuditReport, UserPermission


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


async def team_access_review(
    client: GitHubClient,
    owner: str,
    repo: str | None = None,
    team: str | None = None,
) -> AccessReport:
    """Return an access report for a repo's collaborators or an org's members."""
    admins: list[UserPermission] = []
    writers: list[UserPermission] = []
    readers: list[UserPermission] = []

    if repo:
        collaborators = await client.get_all(
            f"/repos/{owner}/{repo}/collaborators",
            params={"per_page": 100},
        )
        for user in collaborators:
            login = user.get("login", "unknown")
            perms = user.get("permissions", {})
            if perms.get("admin"):
                permission = "admin"
            elif perms.get("push"):
                permission = "write"
            else:
                permission = "read"
            up = UserPermission(login=login, permission=permission, source="direct")
            if permission == "admin":
                admins.append(up)
            elif permission == "write":
                writers.append(up)
            else:
                readers.append(up)
        target = f"{owner}/{repo}"
    else:
        members = await client.get_all(
            f"/orgs/{owner}/members",
            params={"per_page": 100},
        )
        for user in members:
            login = user.get("login", "unknown")
            up = UserPermission(login=login, permission="member", source="org")
            readers.append(up)
        target = f"org:{owner}"

    total = len(admins) + len(writers) + len(readers)
    return AccessReport(
        target=target,
        admins=admins,
        writers=writers,
        readers=readers,
        total_users=total,
    )


async def permission_audit(
    client: GitHubClient,
    owner: str,
) -> PermissionAuditReport:
    """Audit all repos in an org for outside collaborators and direct user access."""
    repos = await client.get_all(f"/orgs/{owner}/repos", params={"per_page": 100})

    findings: list[AuditFinding] = []

    for repo_data in repos:
        repo_name = repo_data.get("name", "unknown")

        # Check for outside collaborators (high severity)
        try:
            outside = await client.get_all(
                f"/repos/{owner}/{repo_name}/collaborators",
                params={"affiliation": "outside", "per_page": 100},
            )
            if outside:
                users = [u.get("login", "unknown") for u in outside]
                findings.append(
                    AuditFinding(
                        repo=repo_name,
                        finding="Outside collaborators with access",
                        severity="high",
                        users=users,
                    )
                )
        except GitHubAPIError:
            pass

        # Check for direct user access bypassing teams (medium severity)
        try:
            direct = await client.get_all(
                f"/repos/{owner}/{repo_name}/collaborators",
                params={"affiliation": "direct", "per_page": 100},
            )
            if direct:
                users = [u.get("login", "unknown") for u in direct]
                findings.append(
                    AuditFinding(
                        repo=repo_name,
                        finding="Direct user access (bypassing teams)",
                        severity="medium",
                        users=users,
                    )
                )
        except GitHubAPIError:
            pass

    high_count = sum(1 for f in findings if f.severity == "high")
    medium_count = sum(1 for f in findings if f.severity == "medium")
    low_count = sum(1 for f in findings if f.severity == "low")

    return PermissionAuditReport(
        org=owner,
        total_repos_scanned=len(repos),
        findings=findings,
        high_count=high_count,
        medium_count=medium_count,
        low_count=low_count,
    )
