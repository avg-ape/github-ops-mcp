import pytest
from github_ops_mcp.github_client import GitHubClient
from github_ops_mcp.tools.issues import triage_issues, stale_issue_report
from github_ops_mcp.tools.pulls import pr_review_dashboard
from github_ops_mcp.tools.repos import repo_health_audit


@pytest.mark.integration
@pytest.mark.asyncio
async def test_triage_issues_real_api():
    client = GitHubClient()
    try:
        report = await triage_issues(client, "pallets", "flask")
        assert report.repo == "pallets/flask"
        assert isinstance(report.total_untriaged, int)
    finally:
        await client.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_stale_issue_report_real_api():
    client = GitHubClient()
    try:
        report = await stale_issue_report(client, "pallets", "flask", days=90)
        assert report.repo == "pallets/flask"
        assert isinstance(report.total_stale, int)
    finally:
        await client.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_repo_health_audit_real_api():
    client = GitHubClient()
    try:
        scorecard = await repo_health_audit(client, "pallets", "flask")
        assert scorecard.repo == "pallets/flask"
        assert 0 <= scorecard.score <= 100
        assert len(scorecard.checks) > 0
    finally:
        await client.close()
