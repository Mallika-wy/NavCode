from dataclasses import dataclass
from types import SimpleNamespace as NS

from navcode.models import api as model_api


def test_json_payload_enforces_one_recorded_attempt_without_client_fallback(monkeypatch, tmp_path):
    @dataclass
    class Usage:
        prompt_tokens: int = 10
        completion_tokens: int = 5
        total_tokens: int = 15
    class Client:
        calls = 0
        def generate(self, request):
            self.calls += 1
            assert request.json_mode is False  # supplied client's fallback disabled
            assert request.extra["response_format"] == {"type": "json_object"}
            return NS(text='{"ok":true}', usage=Usage(), latency_ms=1,
                      raw={"choices": [{"finish_reason": "stop"}], "usage": {"total_tokens": 15}})
    client = Client()
    factory = NS(openai_compat=lambda **kwargs: client)
    monkeypatch.setattr(model_api, "load_client", lambda: (factory, lambda **kw: NS(**kw), lambda *a: a))
    monkeypatch.setattr(model_api, "credentials", lambda: "test-credential-never-logged")
    api = model_api.ModelAPI("qwen3.8-max", tmp_path/"calls.jsonl", max_calls=1, json_output=True)
    result = api.generate("Return JSON", "Test", max_tokens=20)
    assert result["status"] == "ok" and client.calls == 1 and api.calls_used == 1
    assert "test-credential-never-logged" not in (tmp_path/"calls.jsonl").read_text()
