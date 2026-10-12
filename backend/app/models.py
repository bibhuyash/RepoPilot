from typing import Literal

from pydantic import BaseModel, Field, field_validator

RiskCategory = Literal["security", "reliability", "maintainability", "performance", "testing"]
RiskSeverity = Literal["low", "medium", "high", "critical"]


class RepositoryRisk(BaseModel):
    title: str = Field(min_length=3, max_length=120)
    category: RiskCategory
    severity: RiskSeverity
    explanation: str = Field(min_length=8)
    evidence: list[str] = Field(min_length=1)
    affected_files: list[str] = Field(default_factory=list)
    recommendation: str = Field(min_length=8)


class RepositoryReport(BaseModel):
    repository: str
    summary: str = Field(min_length=8)
    overall_risk: RiskSeverity
    risks: list[RepositoryRisk]
    confidence: float = Field(ge=0, le=1)
    files_inspected: int = Field(ge=0)
    issues_inspected: int = Field(ge=0)


class AnalyzeRequest(BaseModel):
    repository_url: str = Field(min_length=1, max_length=300)
    question: str | None = Field(default=None, max_length=500)

    @field_validator("question")
    @classmethod
    def clean_question(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None


class AnalyzeResponse(BaseModel):
    report: RepositoryReport
    trace: list[str]
    request_id: str


class ErrorResponse(BaseModel):
    error: str
    request_id: str


class RepositoryInfo(BaseModel):
    full_name: str
    description: str | None = None
    default_branch: str
    html_url: str
    archived: bool = False


class FileEntry(BaseModel):
    path: str
    size: int = Field(ge=0)


class FileListing(BaseModel):
    files: list[FileEntry]
    truncated: bool = False


class FileContent(BaseModel):
    path: str
    content: str
    truncated: bool = False


class IssueInfo(BaseModel):
    number: int
    title: str
    body: str = ""
    html_url: str


class IssueListing(BaseModel):
    issues: list[IssueInfo]


class DependencyListing(BaseModel):
    manifests: list[str]
