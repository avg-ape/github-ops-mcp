# github-ops-mcp

An MCP server that provides operational tooling over the GitHub API — issue triage, PR review monitoring, repo health audits, and team access reviews. Built for use with [Claude Code](https://docs.anthropic.com/en/docs/claude-code) or Claude Desktop, it gives ops teams a conversational interface to automate the manual toil of managing GitHub-based workflows.

## Quick Start

```bash
git clone https://github.com/avg-ape/github-ops-mcp.git
cd github-ops-mcp
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Optionally set a GitHub token for higher rate limits and write operations:

```bash
cp .env.example .env
# Edit .env and add your token
```

### Use with Claude Code

Add to your Claude Code MCP config (`~/.claude/settings.json`):

```json
{
  "mcpServers": {
    "github-ops": {
      "command": "/path/to/github-ops-mcp/.venv/bin/python",
      "args": ["-m", "github_ops_mcp.server"]
    }
  }
}
```

Then ask Claude things like:
- "Triage untriaged issues in pallets/flask"
- "Show me the PR review dashboard for my-org/my-repo"
- "Run a health audit on fastapi/fastapi"
- "Find stale PRs in my-org/backend that haven't been touched in 14 days"

## Tools

| Tool | Description |
|------|-------------|
| `triage_issues` | Find issues missing labels, assignees, or milestones |
| `bulk_label_issues` | Apply a label to issues matching a text filter (dry-run by default) |
| `stale_issue_report` | Find issues with no activity in N days, grouped by label/assignee |
| `close_resolved_issues` | Bulk-close labeled issues older than N days (dry-run by default) |
| `pr_review_dashboard` | Open PRs grouped by review status with wait times |
| `stale_pr_report` | PRs with no activity in N days |
| `pr_check_status` | CI/check status aggregated across all open PRs |
| `repo_health_audit` | Scorecard: branch protection, CODEOWNERS, CI, license, security policy |
| `repo_compare` | Compare health audits across multiple repos |
| `team_access_review` | List users and permission levels for a repo or org |
| `permission_audit` | Find outside collaborators and direct access bypassing teams |

## Architecture

**GitHub Client (`github_client.py`):** Async HTTP client built on `httpx` — not a wrapper library like PyGitHub. Supports both REST and GraphQL endpoints, automatic pagination via `Link` headers, rate limit tracking, and structured error handling.

**Why httpx over PyGitHub:** Demonstrates understanding of HTTP fundamentals, async patterns, and API design. The client is ~120 lines and does exactly what's needed — no framework overhead.

**REST vs GraphQL:** REST for writes and simple reads. GraphQL for complex queries that would require multiple REST calls (e.g., PR reviews with check status in a single request).

**Pydantic Models (`models.py`):** All tool outputs are typed Pydantic models with human-readable `__str__` methods. Claude gets structured data to reason about, not raw JSON dumps.

**Rate Limiting:** The client reads `X-RateLimit-Remaining` headers and surfaces clear errors when limits are hit. Works unauthenticated for public repos (60 req/hr) or authenticated with a personal access token (5,000 req/hr).

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run unit tests
pytest tests/ -v

# Run integration tests (hits real GitHub API)
pytest tests/ -v --integration
```

## License

MIT
