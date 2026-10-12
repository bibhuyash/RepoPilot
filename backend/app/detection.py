import re

from .security import redact

RULES: list[tuple[str, str, str, re.Pattern[str]]] = [
    ("Potential hard-coded credential", "security", "high", re.compile(r"(?i)(?:api[_-]?key|secret|token|password)\s*[:=]\s*['\"]?(?:[A-Za-z0-9_+./=-]{8,}|\[REDACTED\])")),
    ("Possible SQL injection", "security", "high", re.compile(r"(?i)(?:execute|query)\s*\([^\n]*(?:f['\"]|\.format\(|\+\s*\w+)")),
    ("Unbounded retry loop", "reliability", "high", re.compile(r"(?m)\bwhile\s+True\s*:")),
    ("Unvalidated request input", "security", "medium", re.compile(r"\brequest\.(?:args|query_params)\s*\[")),
    ("Unsafe shell execution", "security", "high", re.compile(r"(?i)subprocess\.(?:run|Popen|call)\([^\n]*shell\s*=\s*True")),
]


def detect_candidates(files: dict[str, str]) -> list[dict[str, str]]:
    found = []
    for path, content in files.items():
        for line_number, line in enumerate(content.splitlines(), start=1):
            if re.search(r"\b(?:requests|httpx)\.(?:get|post|put|delete)\s*\(", line) and "timeout=" not in line and "timeout =" not in line:
                found.append({"title": "HTTP request without timeout", "category": "reliability", "severity": "medium", "path": path, "line": str(line_number), "evidence": redact(line.strip())[:180]})
            for title, category, severity, pattern in RULES:
                if pattern.search(line):
                    found.append({"title": title, "category": category, "severity": severity, "path": path, "line": str(line_number), "evidence": redact(line.strip())[:180]})
    return found[:30]
