import json
import logging
import re
import time
from typing import TypeVar

from mcp import Client
from pydantic import BaseModel

from .github import GitHubError
from .mcp_server import github_mcp
from .models import DependencyListing, FileContent, FileListing, IssueListing, RepositoryInfo

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


class GitHubTools:
    async def call(self, name: str, arguments: dict[str, str], model: type[T], request_id: str) -> T:
        started = time.monotonic()
        success = False
        try:
            async with Client(github_mcp) as client:
                result = await client.call_tool(name, arguments)
            if result.is_error:
                message = "GitHub tool failed."
                for block in result.content:
                    if getattr(block, "type", None) == "text":
                        message = str(block.text)
                        break
                match = re.search(r"RP:(400|403|404|429|502|504):(.+)", message)
                if match:
                    raise GitHubError(match.group(2).strip(), int(match.group(1)))
                status = 502
                raise GitHubError(message, status)
            if result.structured_content is None:
                raise GitHubError("GitHub tool returned no structured data.")
            value = model.model_validate(result.structured_content)
            success = True
            return value
        except GitHubError:
            raise
        except Exception as exc:
            raise GitHubError("GitHub MCP tool is temporarily unavailable.") from exc
        finally:
            logger.info(json.dumps({"request_id": request_id, "mcp_tool": name, "duration_ms": round((time.monotonic() - started) * 1000), "success": success}))

    async def repository(self, owner: str, repo: str, request_id: str) -> RepositoryInfo:
        return await self.call("get_repository", {"owner": owner, "repo": repo}, RepositoryInfo, request_id)

    async def files(self, owner: str, repo: str, request_id: str) -> FileListing:
        return await self.call("list_repository_files", {"owner": owner, "repo": repo}, FileListing, request_id)

    async def file(self, owner: str, repo: str, path: str, request_id: str) -> FileContent:
        return await self.call("read_repository_file", {"owner": owner, "repo": repo, "path": path}, FileContent, request_id)

    async def issues(self, owner: str, repo: str, request_id: str) -> IssueListing:
        return await self.call("list_repository_issues", {"owner": owner, "repo": repo}, IssueListing, request_id)

    async def dependencies(self, owner: str, repo: str, request_id: str) -> DependencyListing:
        return await self.call("get_repository_dependencies", {"owner": owner, "repo": repo}, DependencyListing, request_id)
