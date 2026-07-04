"""Async GitHub API client wrapping httpx.AsyncClient."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import httpx


class GitHubAPIError(Exception):
    """Raised when the GitHub API returns an error response."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


class GitHubClient:
    """Async GitHub API client with rate limit tracking and pagination support."""

    BASE_URL = "https://api.github.com"

    def __init__(self, token: str | None = None) -> None:
        self._token = token or os.environ.get("GITHUB_TOKEN")
        headers: dict[str, str] = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            headers=headers,
            timeout=httpx.Timeout(30.0),
        )

        self.rate_limit_remaining: int | None = None
        self.rate_limit_reset: datetime | None = None

    def _update_rate_limit(self, response: httpx.Response) -> None:
        """Update rate limit tracking from response headers."""
        remaining = response.headers.get("X-RateLimit-Remaining")
        reset = response.headers.get("X-RateLimit-Reset")
        if remaining is not None:
            try:
                self.rate_limit_remaining = int(remaining)
            except ValueError:
                pass
        if reset is not None:
            try:
                self.rate_limit_reset = datetime.fromtimestamp(int(reset), tz=timezone.utc)
            except ValueError:
                pass

    def _check_response(self, response: httpx.Response) -> None:
        """Raise GitHubAPIError for error HTTP status codes."""
        if response.is_success:
            return

        status = response.status_code

        if status == 401:
            raise GitHubAPIError(
                status,
                "Token is invalid or expired. Check your GITHUB_TOKEN.",
            )

        if status == 403:
            try:
                body = response.text.lower()
            except Exception:
                body = ""
            if "rate limit" in body:
                reset_time = (
                    self.rate_limit_reset.isoformat() if self.rate_limit_reset else "unknown"
                )
                raise GitHubAPIError(
                    status,
                    f"Rate limit exceeded. Resets at {reset_time}.",
                )
            raise GitHubAPIError(
                status,
                "Token lacks required scope. Check https://github.com/settings/tokens",
            )

        if status == 404:
            raise GitHubAPIError(
                status,
                "Resource not found. Check the owner and repo name.",
            )

        # Generic 4xx/5xx
        raise GitHubAPIError(status, f"GitHub API error: {status} {response.reason_phrase}")

    async def get(self, path: str, params: dict[str, Any] | None = None) -> dict | list:
        """Send a GET request and return the parsed JSON response."""
        try:
            response = await self._client.get(path, params=params)
        except httpx.ConnectError:
            raise GitHubAPIError(
                0,
                "Could not reach GitHub API. Check your connection.",
            )
        self._update_rate_limit(response)
        self._check_response(response)
        return response.json()

    async def post(self, path: str, json: dict[str, Any] | None = None) -> dict:
        """Send a POST request and return the parsed JSON response. Requires a token."""
        if not self._token:
            raise GitHubAPIError(0, "Token is required for POST requests.")
        try:
            response = await self._client.post(path, json=json)
        except httpx.ConnectError:
            raise GitHubAPIError(
                0,
                "Could not reach GitHub API. Check your connection.",
            )
        self._update_rate_limit(response)
        self._check_response(response)
        return response.json()

    async def patch(self, path: str, json: dict[str, Any] | None = None) -> dict:
        """Send a PATCH request and return the parsed JSON response. Requires a token."""
        if not self._token:
            raise GitHubAPIError(0, "Token is required for PATCH requests.")
        try:
            response = await self._client.patch(path, json=json)
        except httpx.ConnectError:
            raise GitHubAPIError(
                0,
                "Could not reach GitHub API. Check your connection.",
            )
        self._update_rate_limit(response)
        self._check_response(response)
        return response.json()

    async def get_all(self, path: str, params: dict[str, Any] | None = None) -> list[dict]:
        """Paginated GET that follows Link headers. Returns all items across pages."""
        results: list[dict] = []
        next_url: str | None = path
        first = True

        while next_url is not None:
            try:
                if first:
                    response = await self._client.get(next_url, params=params)
                    first = False
                else:
                    # Subsequent pages come from Link headers as absolute URLs.
                    # Extract path+query so httpx base_url merging works correctly.
                    parsed = httpx.URL(next_url)
                    relative = str(parsed.raw_path.decode())
                    response = await self._client.get(relative)
            except httpx.ConnectError:
                raise GitHubAPIError(
                    0,
                    "Could not reach GitHub API. Check your connection.",
                )
            self._update_rate_limit(response)
            self._check_response(response)
            page_data = response.json()
            if isinstance(page_data, list):
                results.extend(page_data)
            else:
                results.append(page_data)

            link_header = response.headers.get("Link")
            next_url = self._parse_next_link(link_header) if link_header else None

        return results

    async def graphql(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
    ) -> dict:
        """POST to /graphql. Requires a token. Returns the `data` field."""
        if not self._token:
            raise GitHubAPIError(0, "Token is required for GraphQL requests.")

        payload: dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables

        try:
            response = await self._client.post("/graphql", json=payload)
        except httpx.ConnectError:
            raise GitHubAPIError(
                0,
                "Could not reach GitHub API. Check your connection.",
            )
        self._update_rate_limit(response)
        self._check_response(response)

        body = response.json()
        if "errors" in body:
            errors = body["errors"]
            msg = errors[0].get("message", "Unknown GraphQL error") if errors else "GraphQL error"
            raise GitHubAPIError(200, f"GraphQL error: {msg}")

        return body.get("data", {})

    async def close(self) -> None:
        """Close the underlying httpx client."""
        await self._client.aclose()

    @staticmethod
    def _parse_next_link(link_header: str | None) -> str | None:
        """Extract the next URL from a Link header value.

        Link header format example:
            <https://api.github.com/repos/owner/repo/issues?page=2>; rel="next",
            <https://api.github.com/repos/owner/repo/issues?page=5>; rel="last"
        """
        if not link_header:
            return None
        for part in link_header.split(","):
            part = part.strip()
            segments = [s.strip() for s in part.split(";")]
            if len(segments) < 2:
                continue
            url_part = segments[0]
            rel_part = segments[1]
            if 'rel="next"' in rel_part:
                # Strip surrounding angle brackets
                if url_part.startswith("<") and url_part.endswith(">"):
                    return url_part[1:-1]
        return None
