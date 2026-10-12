from .models import FileEntry

MAX_FILES = 12
MAX_FILE_BYTES = 12_000
MAX_CONTEXT_CHARS = 60_000
SKIP_DIRS = {"node_modules", "vendor", "dist", "build", "coverage", "target", ".git", "generated"}
SKIP_SUFFIXES = (".lock", ".min.js", ".map", ".png", ".jpg", ".jpeg", ".gif", ".pdf", ".zip", ".wasm")
MANIFEST_NAMES = {"requirements.txt", "pyproject.toml", "package.json", "go.mod", "pom.xml", "cargo.toml"}


def score_path(path: str) -> int:
    lower = path.lower()
    parts = lower.split("/")
    if any(part in SKIP_DIRS for part in parts) or lower.endswith(SKIP_SUFFIXES):
        return -1
    name = parts[-1]
    if name.startswith("readme"):
        return 100
    if name in MANIFEST_NAMES:
        return 95
    if name.startswith("dockerfile") or "docker-compose" in name or ".github/workflows/" in lower:
        return 88
    if any(word in lower for word in ("auth", "security", "config", "settings")):
        return 80
    if any(word in lower for word in ("main.", "app.", "routes", "api", "database", "db.")):
        return 70
    if "test" in lower:
        return 55
    if lower.endswith((".py", ".ts", ".tsx", ".js", ".go", ".java", ".rs")):
        return 30
    return -1


def select_files(files: list[FileEntry]) -> list[str]:
    candidates = [item for item in files if item.size <= MAX_FILE_BYTES and score_path(item.path) >= 0]
    return [item.path for item in sorted(candidates, key=lambda item: (-score_path(item.path), item.path))[:MAX_FILES]]
