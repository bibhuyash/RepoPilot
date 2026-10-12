import re
from urllib.parse import urlparse

from .models import RepositoryReport

OWNER_REPO = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
REPO_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")


def parse_repository_url(value: str) -> tuple[str, str]:
    url = urlparse(value.strip())
    parts = url.path.strip("/").split("/")
    if url.scheme != "https" or url.hostname != "github.com" or url.port is not None or url.username or url.password or url.query or url.fragment or len(parts) != 2:
        raise ValueError("Enter a public GitHub URL such as https://github.com/owner/repo")
    owner, repo = parts
    if repo.endswith(".git"):
        repo = repo[:-4]
    if not OWNER_REPO.fullmatch(owner) or not REPO_NAME.fullmatch(repo) or repo in {".", ".."}:
        raise ValueError("Enter a valid GitHub repository URL")
    return owner, repo


SECRET_PATTERNS = [
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----[\s\S]*?-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"(?i)\b(?:api[_-]?key|secret|token|password|passwd|client[_-]?secret)\b['\"]?\s*[:=]\s*['\"]?([A-Za-z0-9_+./=-]{8,})"),
    re.compile(r"\b(?:AKIA[A-Z0-9]{16}|gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{20,})\b"),
]


def redact(text: str) -> str:
    for pattern in SECRET_PATTERNS:
        if pattern.groups:
            text = pattern.sub(lambda match: match.group(0).replace(match.group(1), "[REDACTED]"), text)
        else:
            text = pattern.sub("[REDACTED]", text)
    return text


def guard_report(report: RepositoryReport, repository: str, source_paths: set[str], evidence: list[str]) -> RepositoryReport:
    report.repository = repository
    allowed = "\n".join(evidence).lower()
    guarded = []
    for risk in report.risks:
        risk.affected_files = [path for path in risk.affected_files if path in source_paths]
        if not risk.evidence or any(item.lower() not in allowed for item in risk.evidence):
            continue
        risk.title = redact(risk.title)
        risk.explanation = redact(risk.explanation)
        risk.evidence = [redact(item) for item in risk.evidence]
        risk.recommendation = redact(risk.recommendation)
        guarded.append(risk)
    report.risks = guarded[:8]
    report.summary = redact(report.summary)
    levels = {"low": 0, "medium": 1, "high": 2, "critical": 3}
    report.overall_risk = max((risk.severity for risk in report.risks), key=lambda x: levels[x], default="low")
    return RepositoryReport.model_validate(report)
