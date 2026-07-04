"""Repo health audit tools for github-ops-mcp."""

from __future__ import annotations

from github_ops_mcp.github_client import GitHubAPIError, GitHubClient
from github_ops_mcp.models import HealthCheck, HealthScorecard, RepoComparison


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _check_branch_protection(
    client: GitHubClient,
    owner: str,
    repo: str,
    branch: str,
) -> HealthCheck:
    """Check whether the given branch has protection rules enabled."""
    try:
        data = await client.get(f"/repos/{owner}/{repo}/branches/{branch}/protection")
        has_pr_review = "required_pull_request_reviews" in data
        if has_pr_review:
            detail = f"Branch protection enabled with required PR reviews on {branch}"
        else:
            detail = f"Branch protection enabled on {branch} (no required PR reviews)"
        return HealthCheck(name="Branch Protection", passed=True, detail=detail)
    except GitHubAPIError as e:
        if e.status_code == 404:
            return HealthCheck(
                name="Branch Protection",
                passed=False,
                detail=f"No branch protection on {branch}",
            )
        if e.status_code in (401, 403):
            return HealthCheck(
                name="Branch Protection",
                passed=False,
                detail="Cannot check — requires authenticated token with repo scope",
            )
        raise


async def _check_codeowners(
    client: GitHubClient,
    owner: str,
    repo: str,
) -> HealthCheck:
    """Check whether a CODEOWNERS file exists in any standard location."""
    paths = ["CODEOWNERS", ".github/CODEOWNERS", "docs/CODEOWNERS"]
    for path in paths:
        try:
            await client.get(f"/repos/{owner}/{repo}/contents/{path}")
            return HealthCheck(
                name="CODEOWNERS",
                passed=True,
                detail=f"CODEOWNERS found at {path}",
            )
        except GitHubAPIError as e:
            if e.status_code == 404:
                continue
            raise
    return HealthCheck(
        name="CODEOWNERS",
        passed=False,
        detail="No CODEOWNERS file found (checked CODEOWNERS, .github/CODEOWNERS, docs/CODEOWNERS)",
    )


async def _check_ci(
    client: GitHubClient,
    owner: str,
    repo: str,
) -> HealthCheck:
    """Check whether any GitHub Actions workflows are configured."""
    try:
        data = await client.get(f"/repos/{owner}/{repo}/actions/workflows")
        total = data.get("total_count", 0) if isinstance(data, dict) else 0
        if total > 0:
            workflows = data.get("workflows", [])
            names = [w.get("name", "unknown") for w in workflows[:5]]
            detail = f"{total} workflow(s) found: {', '.join(names)}"
            return HealthCheck(name="CI/CD", passed=True, detail=detail)
        return HealthCheck(name="CI/CD", passed=False, detail="No GitHub Actions workflows configured")
    except GitHubAPIError as e:
        if e.status_code == 404:
            return HealthCheck(name="CI/CD", passed=False, detail="No GitHub Actions workflows configured")
        raise


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


async def repo_health_audit(
    client: GitHubClient,
    owner: str,
    repo: str,
) -> HealthScorecard:
    """Run a full health audit on a single repo and return a scored scorecard."""
    repo_data = await client.get(f"/repos/{owner}/{repo}")
    default_branch = repo_data.get("default_branch", "main")

    checks: list[HealthCheck] = []

    # License check
    license_info = repo_data.get("license")
    if license_info:
        license_name = license_info.get("name", "unknown")
        checks.append(HealthCheck(name="License", passed=True, detail=f"License: {license_name}"))
    else:
        checks.append(HealthCheck(name="License", passed=False, detail="No license file found"))

    # Branch protection check
    bp_check = await _check_branch_protection(client, owner, repo, default_branch)
    checks.append(bp_check)

    # CODEOWNERS check
    co_check = await _check_codeowners(client, owner, repo)
    checks.append(co_check)

    # CI/CD check
    ci_check = await _check_ci(client, owner, repo)
    checks.append(ci_check)

    # Security policy check (community profile)
    try:
        profile = await client.get(f"/repos/{owner}/{repo}/community/profile")
        files = profile.get("files", {}) if isinstance(profile, dict) else {}
        security = files.get("security") if isinstance(files, dict) else None
        if security:
            checks.append(HealthCheck(name="Security Policy", passed=True, detail="SECURITY.md found"))
        else:
            checks.append(
                HealthCheck(name="Security Policy", passed=False, detail="No SECURITY.md found")
            )
    except GitHubAPIError:
        checks.append(
            HealthCheck(name="Security Policy", passed=False, detail="Could not retrieve community profile")
        )

    # Default branch name check
    if default_branch == "main":
        checks.append(
            HealthCheck(name="Default Branch", passed=True, detail=f"Default branch is '{default_branch}'")
        )
    else:
        checks.append(
            HealthCheck(
                name="Default Branch",
                passed=False,
                detail=f"Default branch is '{default_branch}' (consider renaming to 'main')",
            )
        )

    total = len(checks)
    passed_count = sum(1 for c in checks if c.passed)
    score = int((passed_count / total) * 100) if total > 0 else 0
    recommendations = [c.detail for c in checks if not c.passed]

    return HealthScorecard(
        repo=f"{owner}/{repo}",
        score=score,
        checks=checks,
        recommendations=recommendations,
    )


async def repo_compare(
    client: GitHubClient,
    owner: str,
    repos: list[str],
) -> RepoComparison:
    """Compare health scorecards across multiple repos and highlight inconsistencies."""
    scorecards: list[HealthScorecard] = []
    for repo_name in repos:
        scorecard = await repo_health_audit(client, owner, repo_name)
        scorecards.append(scorecard)

    # Build a map: check_name -> {repo_name: passed}
    check_map: dict[str, dict[str, bool]] = {}
    for scorecard in scorecards:
        repo_short = scorecard.repo.split("/", 1)[-1]
        for check in scorecard.checks:
            if check.name not in check_map:
                check_map[check.name] = {}
            check_map[check.name][repo_short] = check.passed

    inconsistencies: list[str] = []
    for check_name, repo_results in check_map.items():
        passing = [r for r, p in repo_results.items() if p]
        failing = [r for r, p in repo_results.items() if not p]
        if passing and failing:
            inconsistencies.append(
                f"{check_name}: passing in {passing} but failing in {failing}"
            )

    return RepoComparison(
        owner=owner,
        repos=scorecards,
        inconsistencies=inconsistencies,
    )
