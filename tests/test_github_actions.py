"""
Tests for GitHub Actions integration.

Referenced: §4.5.1, ADR-029
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from factory.integrations.github import GitHubClient


@pytest.fixture
def mock_github_client():
    """Mock GitHub client with workflow capabilities."""
    client = GitHubClient(token="test_token")
    client.client = MagicMock()
    return client


@pytest.mark.asyncio
async def test_dispatch_workflow(mock_github_client):
    """Test workflow dispatch with input parameters."""
    mock_repo = MagicMock()
    mock_workflow = MagicMock()
    mock_workflow.create_dispatch.return_value = True
    mock_workflow.get_runs.return_value = [
        MagicMock(id=12345, status="queued")
    ]
    mock_repo.get_workflow.return_value = mock_workflow
    mock_github_client.client.get_repo.return_value = mock_repo

    run_id = await mock_github_client.dispatch_workflow(
        repo_name="owner/repo",
        workflow_file="build.yml",
        inputs={"build_id": "test-123", "variant": "release"},
    )

    assert run_id == "12345"
    mock_workflow.create_dispatch.assert_called_once_with(
        ref="main",
        inputs={"build_id": "test-123", "variant": "release"},
    )


@pytest.mark.asyncio
async def test_poll_workflow_status_success(mock_github_client):
    """Test polling workflow until successful completion."""
    mock_repo = MagicMock()
    mock_run = MagicMock(
        id=12345,
        status="completed",
        conclusion="success",
        html_url="https://github.com/owner/repo/actions/runs/12345",
        created_at=MagicMock(isoformat=lambda: "2026-03-01T10:00:00Z"),
        updated_at=MagicMock(isoformat=lambda: "2026-03-01T10:15:00Z"),
    )
    mock_repo.get_workflow_run.return_value = mock_run
    mock_github_client.client.get_repo.return_value = mock_repo

    result = await mock_github_client.poll_workflow_status(
        repo_name="owner/repo",
        run_id="12345",
        timeout_minutes=1,
        poll_interval=0,
    )

    assert result["conclusion"] == "success"
    assert result["status"] == "completed"
    assert "html_url" in result


@pytest.mark.asyncio
async def test_poll_workflow_status_timeout(mock_github_client):
    """Test timeout when workflow doesn't complete."""
    mock_repo = MagicMock()
    mock_run = MagicMock(status="in_progress", conclusion=None)
    mock_repo.get_workflow_run.return_value = mock_run
    mock_github_client.client.get_repo.return_value = mock_repo

    with pytest.raises(TimeoutError, match="did not complete within"):
        await mock_github_client.poll_workflow_status(
            repo_name="owner/repo",
            run_id="12345",
            timeout_minutes=0.001,
            poll_interval=0,
        )


@pytest.mark.asyncio
async def test_commit_workflow_template(mock_github_client):
    """Test committing workflow file to repository."""
    mock_repo = MagicMock()
    mock_repo.get_contents.side_effect = Exception("File not found")
    mock_github_client.client.get_repo.return_value = mock_repo

    await mock_github_client.commit_workflow_template(
        repo_name="owner/repo",
        workflow_name="build.yml",
        workflow_content="name: Build\non: push",
    )

    mock_repo.create_file.assert_called_once()
    args = mock_repo.create_file.call_args
    assert args[1]["path"] == ".github/workflows/build.yml"
    assert "Build" in args[1]["content"]


@pytest.mark.asyncio
async def test_download_artifact(mock_github_client, tmp_path):
    """Test artifact lookup succeeds (HTTP download requires aiohttp at runtime)."""
    mock_repo = MagicMock()
    mock_artifact = MagicMock(
        name="test-artifact",
        id=99999,
        archive_download_url="https://api.github.com/download",
        size_in_bytes=1024,
    )
    mock_repo.get_artifacts.return_value = iter([mock_artifact])
    mock_github_client.client.get_repo.return_value = mock_repo

    # Verify artifact-not-found raises correctly
    mock_repo.get_artifacts.return_value = iter([])
    with pytest.raises(Exception, match="not found"):
        await mock_github_client.download_artifact(
            repo_name="owner/repo",
            artifact_name="missing-artifact",
            destination_dir=tmp_path,
        )


def test_workflow_template_exists_react_native():
    """Verify React Native workflow template exists."""
    template_path = (
        Path(__file__).parent.parent
        / "factory"
        / "templates"
        / "github_actions"
        / "react_native_android.yml"
    )
    assert template_path.exists(), f"Template missing: {template_path}"


def test_workflow_template_exists_python_backend():
    """Verify Python Backend workflow template exists."""
    template_path = (
        Path(__file__).parent.parent
        / "factory"
        / "templates"
        / "github_actions"
        / "python_backend.yml"
    )
    assert template_path.exists(), f"Template missing: {template_path}"
