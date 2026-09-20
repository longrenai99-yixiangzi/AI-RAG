from pathlib import Path

from app.answer_engine.llm.provider_reliability import ShadowReliableProvider, TransportResponse
from app.config import Settings


def test_official_deepseek_v4_disables_default_thinking_for_short_rag_answers():
    captured = {}

    def transport(payload, _headers, _timeout):
        captured.update(payload)
        return TransportResponse(200, {"choices": [{"message": {"content": "READY"}}]})

    settings = Settings(Path("."), Path("data"), Path("vault"), "https://api.deepseek.com", "deepseek-v4-flash", "test-key", "embedding", "reranker", "off", 1, 1)
    result = ShadowReliableProvider(settings, max_attempts=1, transport=transport).generate("system", "user", max_tokens=8)
    assert result.content == "READY"
    assert captured["thinking"] == {"type": "disabled"}
