"""Unit tests for repo health audit tools."""

from __future__ import annotations

import httpx
import pytest
import respx

from github_ops_mcp.github_client import GitHubClient
from github_ops_mcp.tools.repos import repo_compare, repo_health_audit

RATE_LIMIT_HEADERS = {
    "X-RateLimit-Remaining": "50",
    "X-RateLimit-Reset": "1720100000",
}

BASE = "https://api.github.com"


def _repo_data(name: str, default_branch: str = "main", has_license: bool = True) -> dict:
    return {
        "name": name,
        "default_branch": default_branch,
        "license": {"name": "MIT License", "spdx_id": "MIT"} if has_license else None,
    }


def _workflows_data(count: int = 2) -> dict:
    workflows = [{"name": f"CI workflow {i}"} for i in range(count)]
    return {"total_count": count, "workflows": workflows}


def _community_profile(has_security: bool = True) -> dict:
    return {
        "files": {
            "security": {"url": "https://github.com/owner/repo/security"} if has_security else None,
        }
    }


# ---------------------------------------------------------------------------
# test_repo_health_audit_healthy_repo
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_repo_health_audit_healthy_repo():
    """A repo with all health checks passing should have score > 0 and License + Branch Protection passing."""
    client = GitHubClient(token="test-token")

    with respx.mock:
        # Repo metadata
        respx.get(f"{BASE}/repos/owner/my-repo").mock(
            return_value=httpx.Response(200, json=_repo_data("my-repo"), headers=RATE_LIMIT_HEADERS)
        )

        # Branch protection (200 with required PR reviews)
        respx.get(f"{BASE}/repos/owner/my-repo/branches/main/protection").mock(
            return_value=httpx.Response(
                200,
                json={"required_pull_request_reviews": {"required_approving_review_count": 1}},
                headers=RATE_LIMIT_HEADERS,
            )
        )

        # CODEOWNERS at first path
        respx.get(f"{BASE}/repos/owner/my-repo/contents/CODEOWNERS").mock(
            return_value=httpx.Response(200, json={"name": "CODEOWNERS"}, headers=RATE_LIMIT_HEADERS)
        )

        # CI workflows (count > 0)
        respx.get(f"{BASE}/repos/owner/my-repo/actions/workflows").mock(
            return_value=httpx.Response(200, json=_workflows_data(3), headers=RATE_LIMIT_HEADERS)
        )

        # Community profile with security policy
        respx.get(f"{BASE}/repos/owner/my-repo/community/profile").mock(
            return_value=httpx.Response(200, json=_community_profile(True), headers=RATE_LIMIT_HEADERS)
        )

        scorecard = await repo_health_audit(client, "owner", "my-repo")

    await client.close()

    assert scorecard.repo == "owner/my-repo"
    assert scorecard.score > 0

    check_map = {c.name: c for c in scorecard.checks}

    assert "License" in check_map
    assert check_map["License"].passed is True

    assert "Branch Protection" in check_map
    assert check_map["Branch Protection"].passed is True

    assert "CODEOWNERS" in check_map
    assert check_map["CODEOWNERS"].passed is True

    assert "CI/CD" in check_map
    assert check_map["CI/CD"].passed is True

    assert "Security Policy" in check_map
    assert check_map["Security Policy"].passed is True

    assert "Default Branch" in check_map
    assert check_map["Default Branch"].passed is True

    # Score should be 100 when all pass
    assert scorecard.score == 100
    assert scorecard.recommendations == []


# ---------------------------------------------------------------------------
# test_repo_compare_finds_inconsistencies
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_repo_compare_finds_inconsistencies():
    """repo-a has license, repo-b does not — License should appear in inconsistencies."""
    client = GitHubClient(token="test-token")

    with respx.mock:
        # repo-a: has license
        respx.get(f"{BASE}/repos/owner/repo-a").mock(
            return_value=httpx.Response(200, json=_repo_data("repo-a", has_license=True), headers=RATE_LIMIT_HEADERS)
        )
        # repo-b: no license
        respx.get(f"{BASE}/repos/owner/repo-b").mock(
            return_value=httpx.Response(200, json=_repo_data("repo-b", has_license=False), headers=RATE_LIMIT_HEADERS)
        )

        # Both repos: no branch protection (404)
        respx.get(f"{BASE}/repos/owner/repo-a/branches/main/protection").mock(
            return_value=httpx.Response(404, json={"message": "Not Found"}, headers=RATE_LIMIT_HEADERS)
        )
        respx.get(f"{BASE}/repos/owner/repo-b/branches/main/protection").mock(
            return_value=httpx.Response(404, json={"message": "Not Found"}, headers=RATE_LIMIT_HEADERS)
        )

        # Both repos: no CODEOWNERS (all paths 404)
        for repo_name in ["repo-a", "repo-b"]:
            for path in ["CODEOWNERS", ".github/CODEOWNERS", "docs/CODEOWNERS"]:
                respx.get(f"{BASE}/repos/owner/{repo_name}/contents/{path}").mock(
                    return_value=httpx.Response(404, json={"message": "Not Found"}, headers=RATE_LIMIT_HEADERS)
                )

        # Both repos: 0 workflows
        for repo_name in ["repo-a", "repo-b"]:
            respx.get(f"{BASE}/repos/owner/{repo_name}/actions/workflows").mock(
                return_value=httpx.Response(200, json={"total_count": 0, "workflows": []}, headers=RATE_LIMIT_HEADERS)
            )

        # Both repos: no security policy in community profile
        for repo_name in ["repo-a", "repo-b"]:
            respx.get(f"{BASE}/repos/owner/{repo_name}/community/profile").mock(
                return_value=httpx.Response(200, json=_community_profile(False), headers=RATE_LIMIT_HEADERS)
            )

        comparison = await repo_compare(client, "owner", ["repo-a", "repo-b"])

    await client.close()

    assert comparison.owner == "owner"
    assert len(comparison.repos) == 2

    # License is inconsistent: repo-a passes, repo-b fails
    inconsistent_checks = " ".join(comparison.inconsistencies)
    assert "License" in inconsistent_checks
