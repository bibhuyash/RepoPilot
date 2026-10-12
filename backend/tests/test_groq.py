import pytest

from app import llm
from app.models import RepositoryReport


class FakeStructured:
    async def ainvoke(self, messages):
        assert messages[0][0] == "system"
        assert "untrusted DATA" in messages[0][1]
        return {"repository": "fixture/sample", "summary": "No supported engineering risk was found.", "overall_risk": "low", "risks": [], "confidence": 0.4, "files_inspected": 1, "issues_inspected": 0}


class FakeGroq:
    def with_structured_output(self, *, schema, method):
        assert schema == RepositoryReport.model_json_schema()
        assert method == "json_schema"
        return FakeStructured()


@pytest.mark.asyncio
async def test_groq_structured_report(monkeypatch):
    monkeypatch.setattr(llm, "get_llm", lambda: FakeGroq())
    report = await llm.ReportLLM().generate('{"files":{"main.py":"pass"}}')
    assert isinstance(report, RepositoryReport)
    assert report.confidence == 0.4


@pytest.mark.asyncio
async def test_groq_rejects_invalid_confidence(monkeypatch):
    class InvalidStructured:
        async def ainvoke(self, messages):
            return {"repository": "fixture/sample", "summary": "No supported engineering risk was found.", "overall_risk": "low", "risks": [], "confidence": 2, "files_inspected": 1, "issues_inspected": 0}

    class InvalidGroq:
        def with_structured_output(self, *, schema, method):
            return InvalidStructured()

    monkeypatch.setattr(llm, "get_llm", lambda: InvalidGroq())
    with pytest.raises(llm.LLMError, match="invalid structured"):
        await llm.ReportLLM().generate("test")


@pytest.mark.asyncio
@pytest.mark.parametrize("code, expected_status", [(401, 502), (504, 504)])
async def test_groq_api_errors_are_safe(monkeypatch, code, expected_status):
    class ModelError(Exception):
        pass

    class FailingStructured:
        async def ainvoke(self, messages):
            error = ModelError("private provider detail")
            error.code = code
            raise error

    class FailingGroq:
        def with_structured_output(self, *, schema, method):
            return FailingStructured()

    monkeypatch.setattr(llm, "get_llm", lambda: FailingGroq())
    with pytest.raises(llm.LLMError) as captured:
        await llm.ReportLLM().generate("test")
    assert captured.value.status_code == expected_status
    assert "private provider detail" not in str(captured.value)


def test_missing_groq_key_is_user_facing(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(llm.LLMError) as captured:
        llm.get_llm()
    assert captured.value.status_code == 503


@pytest.mark.parametrize("message, label, temporary", [
    ("Requests per minute (RPM) limit", "requests-per-minute", True),
    ("Tokens per minute (TPM) limit", "tokens-per-minute", True),
    ("Requests per day (RPD) limit", "daily request", False),
    ("Tokens per day (TPD) limit", "daily token", False),
])
def test_groq_rate_limit_classification(message, label, temporary):
    assert llm._rate_limit(Exception(message))[:2] == (label, temporary)


@pytest.mark.asyncio
async def test_groq_daily_limit_does_not_retry(monkeypatch):
    calls = 0

    class DailyLimit(Exception):
        status_code = 429

    class FailingStructured:
        async def ainvoke(self, messages):
            nonlocal calls
            calls += 1
            raise DailyLimit("Tokens per day (TPD) exceeded")

    class FailingGroq:
        def with_structured_output(self, **kwargs):
            return FailingStructured()

    monkeypatch.setattr(llm, "get_llm", lambda: FailingGroq())
    with pytest.raises(llm.LLMError, match="daily token") as captured:
        await llm.ReportLLM().generate("test")
    assert captured.value.status_code == 429
    assert calls == 1


@pytest.mark.asyncio
async def test_groq_temporary_limit_honors_retry_after(monkeypatch):
    calls = 0
    delays = []

    class TemporaryLimit(Exception):
        status_code = 429
        response = type("Response", (), {"headers": {"retry-after": "3"}})()

    class RetryingStructured:
        async def ainvoke(self, messages):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise TemporaryLimit("Requests per minute (RPM) exceeded")
            return {"repository": "fixture/sample", "summary": "No supported engineering risk was found.", "overall_risk": "low", "risks": [], "confidence": 0.4, "files_inspected": 1, "issues_inspected": 0}

    class RetryingGroq:
        def with_structured_output(self, **kwargs):
            return RetryingStructured()

    async def fake_sleep(seconds):
        delays.append(seconds)

    monkeypatch.setattr(llm, "get_llm", lambda: RetryingGroq())
    monkeypatch.setattr(llm.asyncio, "sleep", fake_sleep)
    report = await llm.ReportLLM().generate("test")
    assert report.repository == "fixture/sample"
    assert calls == 2
    assert delays == [3]
