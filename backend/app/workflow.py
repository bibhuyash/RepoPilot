import json
import logging
import time
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from .detection import detect_candidates
from .github import GitHubError
from .llm import LLMError, ReportLLM
from .mcp_client import GitHubTools
from .models import FileListing, RepositoryReport
from .security import guard_report, parse_repository_url, redact
from .selection import MAX_CONTEXT_CHARS, select_files

logger = logging.getLogger(__name__)


class RepoState(TypedDict, total=False):
    repository_url: str
    question: str | None
    request_id: str
    owner: str
    repo: str
    metadata: dict
    file_paths: list[str]
    _file_listing: FileListing
    selected_files: list[str]
    file_contents: dict[str, str]
    issues: list[dict]
    dependencies: list[str]
    candidate_risks: list[dict]
    report: RepositoryReport
    trace: list[str]
    error: str
    status_code: int


STEPS = {
    "validate_repository": "Repository validated",
    "load_repository": "Repository metadata loaded",
    "inspect_structure": "Repository structure inspected",
    "select_important_files": "Important files selected",
    "inspect_code": "Selected files inspected",
    "inspect_issues": "Issues inspected",
    "inspect_dependencies": "Dependencies inspected",
    "correlate_risks": "Risks correlated",
    "generate_report": "Report generated",
    "guard_report": "Report checked",
}

# Keep one Groq request comfortably below the free-tier token-per-minute limit.
# Candidate evidence preserves findings outside each file's leading excerpt.
PROMPT_FILE_CHARS = 800
PROMPT_ISSUES = 6
PROMPT_ISSUE_BODY_CHARS = 300
PROMPT_DEPENDENCY_CHARS = 600
PROMPT_CANDIDATES = 12


class Investigator:
    def __init__(self, tools: GitHubTools | None = None, llm: ReportLLM | None = None) -> None:
        self.tools = tools or GitHubTools()
        self.llm = llm or ReportLLM()
        graph = StateGraph(RepoState)
        names = list(STEPS)
        for name in names:
            graph.add_node(name, self._wrap(name, getattr(self, name)))
        graph.add_edge(START, names[0])
        for current, following in zip(names, names[1:]):
            graph.add_conditional_edges(current, lambda state: "stop" if state.get("error") else "next", {"stop": END, "next": following})
        graph.add_edge(names[-1], END)
        self.graph = graph.compile()

    def _wrap(self, name: str, function):
        async def wrapped(state: RepoState) -> dict:
            started = time.monotonic()
            success = False
            try:
                update = await function(state)
                update["trace"] = state.get("trace", []) + [STEPS[name]]
                success = True
                return update
            except (ValueError, GitHubError, LLMError) as exc:
                return {"error": str(exc), "status_code": getattr(exc, "status_code", 400 if isinstance(exc, ValueError) else 502), "trace": state.get("trace", [])}
            finally:
                logger.info(json.dumps({"request_id": state["request_id"], "graph_node": name, "duration_ms": round((time.monotonic() - started) * 1000), "success": success}))
        return wrapped

    async def validate_repository(self, state: RepoState) -> dict:
        owner, repo = parse_repository_url(state["repository_url"])
        return {"owner": owner, "repo": repo}

    async def load_repository(self, state: RepoState) -> dict:
        info = await self.tools.repository(state["owner"], state["repo"], state["request_id"])
        metadata = info.model_dump()
        metadata["description"] = redact(metadata.get("description") or "")
        return {"metadata": metadata}

    async def inspect_structure(self, state: RepoState) -> dict:
        listing = await self.tools.files(state["owner"], state["repo"], state["request_id"])
        return {"file_paths": [file.path for file in listing.files], "_file_listing": listing}

    async def select_important_files(self, state: RepoState) -> dict:
        return {"selected_files": select_files(state["_file_listing"].files)}

    async def inspect_code(self, state: RepoState) -> dict:
        contents: dict[str, str] = {}
        budget = MAX_CONTEXT_CHARS
        for path in state["selected_files"]:
            if budget <= 0:
                break
            try:
                file = await self.tools.file(state["owner"], state["repo"], path, state["request_id"])
            except GitHubError:
                continue
            content = redact(file.content[:budget])
            contents[path] = content
            budget -= len(content)
        return {"file_contents": contents}

    async def inspect_issues(self, state: RepoState) -> dict:
        try:
            listing = await self.tools.issues(state["owner"], state["repo"], state["request_id"])
        except GitHubError:
            return {"issues": []}
        return {"issues": [{"title": redact(issue.title), "body": redact(issue.body), "url": issue.html_url} for issue in listing.issues]}

    async def inspect_dependencies(self, state: RepoState) -> dict:
        try:
            listing = await self.tools.dependencies(state["owner"], state["repo"], state["request_id"])
        except GitHubError:
            return {"dependencies": []}
        return {"dependencies": [redact(item) for item in listing.manifests]}

    async def correlate_risks(self, state: RepoState) -> dict:
        return {"candidate_risks": detect_candidates(state["file_contents"])}

    def evidence(self, state: RepoState) -> list[str]:
        chunks = [redact(state["metadata"].get("description") or "")]
        chunks += list(state["file_contents"].values())
        chunks += [issue["title"] + "\n" + issue["body"] for issue in state["issues"]]
        chunks += state["dependencies"]
        return chunks

    async def generate_report(self, state: RepoState) -> dict:
        repository = f"{state['owner']}/{state['repo']}"
        if not state["file_contents"] and not state["issues"] and not state["dependencies"]:
            return {"report": RepositoryReport(repository=repository, summary="Insufficient readable repository data to assess engineering risk.", overall_risk="low", risks=[], confidence=0.1, files_inspected=0, issues_inspected=0)}
        metadata = state["metadata"]
        payload = json.dumps({
            "repository": repository,
            "question": state.get("question"),
            "metadata": {"full_name": metadata.get("full_name"), "description": (metadata.get("description") or "")[:300], "archived": metadata.get("archived", False)},
            "files": {path: content[:PROMPT_FILE_CHARS] for path, content in state["file_contents"].items()},
            "issues": [{"title": issue["title"], "body": issue["body"][:PROMPT_ISSUE_BODY_CHARS], "url": issue["url"]} for issue in state["issues"][:PROMPT_ISSUES]],
            "dependencies": [item[:PROMPT_DEPENDENCY_CHARS] for item in state["dependencies"][:4]],
            "candidate_risks": state["candidate_risks"][:PROMPT_CANDIDATES],
            "required_files_inspected": len(state["file_contents"]),
            "required_issues_inspected": len(state["issues"]),
        }, ensure_ascii=False)
        report = await self.llm.generate(payload)
        return {"report": report}

    async def guard_report(self, state: RepoState) -> dict:
        report = guard_report(state["report"], f"{state['owner']}/{state['repo']}", set(state["file_contents"]), self.evidence(state))
        report.files_inspected = len(state["file_contents"])
        report.issues_inspected = len(state["issues"])
        if not state["file_contents"]:
            report.confidence = min(report.confidence, 0.3)
        elif len(state["file_contents"]) == 1 and not state["issues"] and not state["dependencies"]:
            report.confidence = min(report.confidence, 0.4)
        return {"report": report}

    async def analyze(self, repository_url: str, question: str | None, request_id: str) -> RepoState:
        return await self.graph.ainvoke({"repository_url": repository_url, "question": question, "request_id": request_id, "trace": []})
