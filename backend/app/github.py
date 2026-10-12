import base64
from urllib.parse import quote

import httpx

from .config import github_token
from .models import DependencyListing, FileContent, FileEntry, FileListing, IssueInfo, IssueListing, RepositoryInfo
from .selection import MAX_FILE_BYTES, MANIFEST_NAMES


class GitHubError(Exception):
    def __init__(self, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


class GitHubAPI:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "RepoPilot"}
        if github_token():
            headers["Authorization"] = f"Bearer {github_token()}"
        self.client = httpx.AsyncClient(base_url="https://api.github.com", headers=headers, timeout=httpx.Timeout(10.0), transport=transport)

    async def __aenter__(self) -> "GitHubAPI":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.client.aclose()

    async def get(self, path: str, params: dict[str, str | int] | None = None) -> object:
        try:
            response = await self.client.get(path, params=params)
        except httpx.TimeoutException as exc:
            raise GitHubError("GitHub timed out. Please try again.", 504) from exc
        except httpx.HTTPError as exc:
            raise GitHubError("GitHub is temporarily unavailable.") from exc
        if response.status_code in (403, 429) and (response.headers.get("X-RateLimit-Remaining") == "0" or response.status_code == 429):
            raise GitHubError("GitHub API rate limit reached. Try again later or configure GITHUB_TOKEN.", 429)
        if response.status_code == 404:
            raise GitHubError("Repository or file not found. Only public repositories are supported.", 404)
        if response.status_code == 403:
            raise GitHubError("GitHub denied access to this repository.", 403)
        if response.status_code >= 400:
            raise GitHubError(f"GitHub returned HTTP {response.status_code}.")
        if len(response.content) > 8_000_000:
            raise GitHubError("GitHub response exceeded the size limit.")
        return response.json()

    @staticmethod
    def repo_path(owner: str, repo: str) -> str:
        return f"/repos/{quote(owner, safe='')}/{quote(repo, safe='')}"

    async def repository(self, owner: str, repo: str) -> RepositoryInfo:
        data = await self.get(self.repo_path(owner, repo))
        if not isinstance(data, dict) or data.get("private") is True:
            raise GitHubError("Only public repositories are supported.", 404)
        return RepositoryInfo.model_validate(data)

    async def files(self, owner: str, repo: str) -> FileListing:
        metadata = await self.repository(owner, repo)
        branch = quote(metadata.default_branch, safe="")
        data = await self.get(f"{self.repo_path(owner, repo)}/git/trees/{branch}", {"recursive": "1"})
        if not isinstance(data, dict):
            raise GitHubError("Unexpected GitHub tree response.")
        files = [FileEntry(path=item["path"], size=item.get("size", 0)) for item in data.get("tree", []) if item.get("type") == "blob" and item.get("size", 0) <= MAX_FILE_BYTES]
        return FileListing(files=files[:5000], truncated=bool(data.get("truncated")) or len(files) > 5000)

    async def file(self, owner: str, repo: str, path: str) -> FileContent:
        if not path or path.startswith("/") or ".." in path.split("/"):
            raise GitHubError("Invalid repository file path.", 400)
        data = await self.get(f"{self.repo_path(owner, repo)}/contents/{quote(path, safe='/')}")
        if not isinstance(data, dict) or data.get("type") != "file" or data.get("encoding") != "base64":
            raise GitHubError("Unsupported repository file.", 400)
        if data.get("size", 0) > MAX_FILE_BYTES:
            raise GitHubError("Repository file exceeds the analysis size limit.", 400)
        raw = base64.b64decode(data.get("content", ""), validate=False)
        if b"\x00" in raw:
            raise GitHubError("Binary repository file is not supported.", 400)
        content = raw.decode("utf-8", errors="replace")
        return FileContent(path=path, content=content[:MAX_FILE_BYTES], truncated=len(content) > MAX_FILE_BYTES)

    async def issues(self, owner: str, repo: str) -> IssueListing:
        data = await self.get(f"{self.repo_path(owner, repo)}/issues", {"state": "open", "per_page": 30})
        if not isinstance(data, list):
            raise GitHubError("Unexpected GitHub issues response.")
        return IssueListing(issues=[IssueInfo(number=item["number"], title=item["title"][:200], body=(item.get("body") or "")[:1000], html_url=item["html_url"]) for item in data if "pull_request" not in item][:20])

    async def dependencies(self, owner: str, repo: str) -> DependencyListing:
        listing = await self.files(owner, repo)
        paths = [item.path for item in listing.files if item.path.lower().split("/")[-1] in MANIFEST_NAMES][:4]
        manifests = []
        for path in paths:
            try:
                file = await self.file(owner, repo, path)
                manifests.append(f"{path}:\n{file.content[:4000]}")
            except GitHubError:
                continue
        return DependencyListing(manifests=manifests)
