import json
from pathlib import Path

import pytest

from app.detection import detect_candidates
from app.security import redact

FIXTURES = json.loads((Path(__file__).parent / "fixtures.json").read_text())


@pytest.mark.parametrize("fixture", FIXTURES, ids=lambda item: item["name"])
def test_known_scenarios(fixture):
    candidates = detect_candidates({fixture["path"]: fixture["code"]})
    titles = {item["title"] for item in candidates}
    if fixture["expected"] is None:
        assert not titles
    else:
        assert fixture["expected"] in titles
    if fixture["name"] == "hard-coded credential":
        assert "1234567890abcdef" not in redact(fixture["code"])
        assert all("1234567890abcdef" not in item["evidence"] for item in candidates)
