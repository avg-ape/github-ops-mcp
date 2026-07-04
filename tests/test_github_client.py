"""Unit tests for GitHubClient."""

from __future__ import annotations

import os

import httpx
import pytest
import respx

from github_ops_mcp.github_client import GitHubAPIError, GitHubClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

RATE_HEADERS = {
    "X-RateLimit-Remaining": "59",
    "X-RateLimit-Reset": "1700000000",
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_returns_json():
    """Mock a 200 GET, verify JSON returned and rate_limit_remaining updated."""
    client = GitHubClient(token="test-token")
    with respx.mock:
        respx.get("https://api.github.com/repos/owner/repo").mock(
            return_value=httpx.Response(
                200,
                json={"id": 1, "name": "repo"},
                headers=RATE_HEADERS,
            )
        )
        result = await client.get("/repos/owner/repo")

    assert result == {"id": 1, "name": "repo"}
    assert client.rate_limit_remaining == 59
    await client.close()


@pytest.mark.asyncio
async def test_401_raises_auth_error():
    """Mock 401, verify GitHubAPIError with auth message."""
    client = GitHubClient(token="bad-token")
    with respx.mock:
        respx.get("https://api.github.com/user").mock(
            return_value=httpx.Response(
                401,
                json={"message": "Bad credentials"},
                headers=RATE_HEADERS,
            )
        )
        with pytest.raises(GitHubAPIError) as exc_info:
            await client.get("/user")

    assert exc_info.value.status_code == 401
    assert "invalid or expired" in exc_info.value.message
    await client.close()


@pytest.mark.asyncio
async def test_404_raises_not_found():
    """Mock 404, verify GitHubAPIError with not found message."""
    client = GitHubClient(token="test-token")
    with respx.mock:
        respx.get("https://api.github.com/repos/nonexistent/repo").mock(
            return_value=httpx.Response(
                404,
                json={"message": "Not Found"},
                headers=RATE_HEADERS,
            )
        )
        with pytest.raises(GitHubAPIError) as exc_info:
            await client.get("/repos/nonexistent/repo")

    assert exc_info.value.status_code == 404
    assert "not found" in exc_info.value.message.lower()
    await client.close()


@pytest.mark.asyncio
async def test_403_rate_limit_raises():
    """Mock 403 with 'rate limit' text, verify rate limit error message."""
    client = GitHubClient(token="test-token")
    with respx.mock:
        respx.get("https://api.github.com/repos/owner/repo").mock(
            return_value=httpx.Response(
                403,
                text="API rate limit exceeded for user ID 123.",
                headers={
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": "1700000000",
                    "Content-Type": "text/plain",
                },
            )
        )
        with pytest.raises(GitHubAPIError) as exc_info:
            await client.get("/repos/owner/repo")

    assert exc_info.value.status_code == 403
    assert "rate limit" in exc_info.value.message.lower()
    await client.close()


@pytest.mark.asyncio
async def test_post_without_token_raises():
    """Client with no token raises an error on POST."""
    os.environ.pop("GITHUB_TOKEN", None)
    client = GitHubClient(token=None)
    with pytest.raises(GitHubAPIError) as exc_info:
        await client.post("/repos/owner/repo/issues", json={"title": "test"})

    assert exc_info.value.status_code == 0
    assert "required" in exc_info.value.message.lower()
    await client.close()


@pytest.mark.asyncio
async def test_get_all_pages_follows_link_headers():
    """Mock two pages with Link header, verify all items are returned."""
    client = GitHubClient(token="test-token")
    page1_items = [{"id": 1}, {"id": 2}]
    page2_items = [{"id": 3}, {"id": 4}]
    page2_url = "https://api.github.com/repos/owner/repo/issues?page=2"

    with respx.mock:
        # Register the more-specific page-2 route first so respx matches it
        # before the catch-all page-1 route (no query params).
        respx.get(page2_url).mock(
            return_value=httpx.Response(
                200,
                json=page2_items,
                headers=RATE_HEADERS,
            )
        )
        # First page
        respx.get("https://api.github.com/repos/owner/repo/issues").mock(
            return_value=httpx.Response(
                200,
                json=page1_items,
                headers={
                    **RATE_HEADERS,
                    "Link": f'<{page2_url}>; rel="next", <https://api.github.com/repos/owner/repo/issues?page=2>; rel="last"',
                },
            )
        )
        results = await client.get_all("/repos/owner/repo/issues")

    assert results == page1_items + page2_items
    await client.close()


@pytest.mark.asyncio
async def test_get_all_pages_no_link_header():
    """Single page with no Link header returns items directly."""
    client = GitHubClient(token="test-token")
    items = [{"id": 1}, {"id": 2}]

    with respx.mock:
        respx.get("https://api.github.com/repos/owner/repo/issues").mock(
            return_value=httpx.Response(
                200,
                json=items,
                headers=RATE_HEADERS,
            )
        )
        results = await client.get_all("/repos/owner/repo/issues")

    assert results == items
    await client.close()


@pytest.mark.asyncio
async def test_graphql_returns_data():
    """Mock GraphQL POST, verify data field is returned."""
    client = GitHubClient(token="test-token")
    query = "query { viewer { login } }"
    response_data = {"viewer": {"login": "octocat"}}

    with respx.mock:
        respx.post("https://api.github.com/graphql").mock(
            return_value=httpx.Response(
                200,
                json={"data": response_data},
                headers=RATE_HEADERS,
            )
        )
        result = await client.graphql(query)

    assert result == response_data
    await client.close()


@pytest.mark.asyncio
async def test_graphql_without_token_raises():
    """Client without token raises GitHubAPIError for GraphQL."""
    os.environ.pop("GITHUB_TOKEN", None)
    client = GitHubClient(token=None)
    with pytest.raises(GitHubAPIError) as exc_info:
        await client.graphql("query { viewer { login } }")

    assert exc_info.value.status_code == 0
    assert "required" in exc_info.value.message.lower()
    await client.close()
