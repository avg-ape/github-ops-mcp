"""Unit tests for team access and permission audit tools."""

from __future__ import annotations

import httpx
import pytest
import respx

from github_ops_mcp.github_client import GitHubClient
from github_ops_mcp.tools.teams import permission_audit, team_access_review

RATE_LIMIT_HEADERS = {
    "X-RateLimit-Remaining": "50",
    "X-RateLimit-Reset": "1720100000",
}

BASE = "https://api.github.com"


def _make_collaborator(login: str, admin: bool = False, push: bool = False, pull: bool = True) -> dict:
    return {
        "login": login,
        "permissions": {
            "admin": admin,
            "push": push,
            "pull": pull,
        },
    }


# ---------------------------------------------------------------------------
# test_team_access_review_repo_level
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_team_access_review_repo_level():
    """3 collaborators: one admin, one writer, one reader — verify totals and grouping."""
    collaborators = [
        _make_collaborator("alice", admin=True, push=True, pull=True),
        _make_collaborator("bob", admin=False, push=True, pull=True),
        _make_collaborator("carol", admin=False, push=False, pull=True),
    ]

    client = GitHubClient(token="test-token")

    with respx.mock:
        respx.get(f"{BASE}/repos/owner/my-repo/collaborators").mock(
            return_value=httpx.Response(200, json=collaborators, headers=RATE_LIMIT_HEADERS)
        )

        report = await team_access_review(client, "owner", repo="my-repo")

    await client.close()

    assert report.target == "owner/my-repo"
    assert report.total_users == 3

    assert len(report.admins) == 1
    assert report.admins[0].login == "alice"
    assert report.admins[0].permission == "admin"
    assert report.admins[0].source == "direct"

    assert len(report.writers) == 1
    assert report.writers[0].login == "bob"
    assert report.writers[0].permission == "write"
    assert report.writers[0].source == "direct"

    assert len(report.readers) == 1
    assert report.readers[0].login == "carol"
    assert report.readers[0].permission == "read"
    assert report.readers[0].source == "direct"


# ---------------------------------------------------------------------------
# test_permission_audit_finds_outside_collaborators
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_permission_audit_finds_outside_collaborators():
    """repo-a has one outside collaborator (high), repo-b has one direct collaborator (medium)."""
    org_repos = [
        {"name": "repo-a"},
        {"name": "repo-b"},
    ]

    outside_user = {"login": "ext-contractor"}
    direct_user = {"login": "direct-dev"}

    client = GitHubClient(token="test-token")

    with respx.mock:
        # Org repos list
        respx.get(f"{BASE}/orgs/myorg/repos").mock(
            return_value=httpx.Response(200, json=org_repos, headers=RATE_LIMIT_HEADERS)
        )

        # repo-a: one outside collaborator, no direct
        respx.get(
            f"{BASE}/repos/myorg/repo-a/collaborators",
            params__contains={"affiliation": "outside"},
        ).mock(
            return_value=httpx.Response(200, json=[outside_user], headers=RATE_LIMIT_HEADERS)
        )
        respx.get(
            f"{BASE}/repos/myorg/repo-a/collaborators",
            params__contains={"affiliation": "direct"},
        ).mock(
            return_value=httpx.Response(200, json=[], headers=RATE_LIMIT_HEADERS)
        )

        # repo-b: no outside, one direct collaborator
        respx.get(
            f"{BASE}/repos/myorg/repo-b/collaborators",
            params__contains={"affiliation": "outside"},
        ).mock(
            return_value=httpx.Response(200, json=[], headers=RATE_LIMIT_HEADERS)
        )
        respx.get(
            f"{BASE}/repos/myorg/repo-b/collaborators",
            params__contains={"affiliation": "direct"},
        ).mock(
            return_value=httpx.Response(200, json=[direct_user], headers=RATE_LIMIT_HEADERS)
        )

        audit = await permission_audit(client, "myorg")

    await client.close()

    assert audit.org == "myorg"
    assert audit.total_repos_scanned == 2

    assert audit.high_count == 1
    assert audit.medium_count == 1
    assert audit.low_count == 0

    high_findings = [f for f in audit.findings if f.severity == "high"]
    assert len(high_findings) == 1
    assert high_findings[0].repo == "repo-a"
    assert "ext-contractor" in high_findings[0].users

    medium_findings = [f for f in audit.findings if f.severity == "medium"]
    assert len(medium_findings) == 1
    assert medium_findings[0].repo == "repo-b"
    assert "direct-dev" in medium_findings[0].users
