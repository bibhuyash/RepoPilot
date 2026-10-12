from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from .github import GitHubAPI, GitHubError
from .models import DependencyListing, FileContent, FileListing, IssueListing, RepositoryInfo

github_mcp = MCPServer("RepoPilot GitHub read-only tools")


async def _invoke(operation):
    try:
        return await operation
    except GitHubError as exc:
        raise ToolError(f"RP:{exc.status_code}:{exc}") from None


@github_mcp.tool()
async def get_repository(owner: str, repo: str) -> RepositoryInfo:
    """Read public repository metadata."""
    async with GitHubAPI() as github:
        return await _invoke(github.repository(owner, repo))


@github_mcp.tool()
async def list_repository_files(owner: str, repo: str) -> FileListing:
    """List bounded file paths in a public repository."""
    async with GitHubAPI() as github:
        return await _invoke(github.files(owner, repo))


@github_mcp.tool()
async def read_repository_file(owner: str, repo: str, path: str) -> FileContent:
    """Read one bounded text file from a public repository."""
    async with GitHubAPI() as github:
        return await _invoke(github.file(owner, repo, path))


@github_mcp.tool()
async def list_repository_issues(owner: str, repo: str) -> IssueListing:
    """List recent open issues, excluding pull requests."""
    async with GitHubAPI() as github:
        return await _invoke(github.issues(owner, repo))


@github_mcp.tool()
async def get_repository_dependencies(owner: str, repo: str) -> DependencyListing:
    """Read a bounded selection of dependency manifests."""
    async with GitHubAPI() as github:
        return await _invoke(github.dependencies(owner, repo))
