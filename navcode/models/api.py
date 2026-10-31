"""Auditable DMXAPI adapter using the user-specified standalone model_client.

No evaluator/agent code is imported from RollbackNav. Credentials never enter
request records or workers. No automatic retries: every attempt has a budget slot.
"""
from __future__ import annotations

import base64
import importlib.util
import json
import os
import sys
import time
from dataclasses import asdict
from pathlib import Path

from navcode.paths import PROJECT_ROOT

ROOT = PROJECT_ROOT


class ModelAPIError(RuntimeError):
    """Model transport/output failure, distinct from a policy/program exception."""


def load_client():
    name = "navcode_external_model_client"
    if name not in sys.modules:
        path = Path(os.environ.get("NAVCODE_MODEL_CLIENT", "/home1/gmh/wangyang/vln/RollbackNav/model_client"))
        spec = importlib.util.spec_from_file_location(name, path / "__init__.py",
                                                     submodule_search_locations=[str(path)])
        package = importlib.util.module_from_spec(spec)
        sys.modules[name] = package
        spec.loader.exec_module(package)
    from navcode_external_model_client.factory import ModelClientFactory
    from navcode_external_model_client.types import ChatRequest, ChatMessage
    return ModelClientFactory, ChatRequest, ChatMessage


def credentials():
    values = {}
    env_path = ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            key, sep, value = line.strip().partition("=")
            if sep and not key.startswith("#"):
                values[key] = value.strip().strip("\"'")
    token = os.environ.get("DMXAPI_TOKEN") or values.get("DMXAPI_TOKEN")
    if not token:
        raise RuntimeError("DMXAPI_TOKEN missing")
    return token


class ModelAPI:
    def __init__(self, model, log_path, max_calls=8, timeout=60, json_output=False):
        factory, self.Request, self.Message = load_client()
        self.model = model
        self.path = Path(log_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.max_calls = max_calls
        self.extra = ({"thinking": {"type": "disabled"}} if model.startswith("deepseek-")
                      else {"enable_thinking": False} if model.startswith("qwen") else {})
        if json_output:
            # Request JSON mode through explicit payload fields, while leaving
            # the supplied client's automatic fallback/retry flag disabled.
            self.extra["response_format"] = {"type": "json_object"}
        self.client = factory.openai_compat(
            base_url=os.environ.get("DMXAPI_BASE_URL", "https://www.dmxapi.cn/v1"),
            model=model, api_key=credentials(), timeout_s=timeout)

    def generate(self, system, user, images=(), max_tokens=1024):
        # The append-only file is also the persistent attempt cap for this run.
        calls = len(self.path.read_text().splitlines()) if self.path.exists() else 0
        if calls >= self.max_calls:
            raise RuntimeError("model call budget exhausted")
        if not 1 <= max_tokens <= 4096:
            raise ValueError("output token cap must be 1..4096")
        content = [{"type": "text", "text": user}]
        for path in images:
            encoded = base64.b64encode(Path(path).read_bytes()).decode()
            content.append({"type": "image_url", "image_url": {
                "url": "data:image/png;base64," + encoded}})
        record = {"attempt": calls + 1, "model": self.model, "time": time.time(),
                  "system": system, "user": user, "images": list(map(str, images)),
                  "max_tokens": max_tokens, "extra": self.extra, "status": "started", "cost_rmb": None}
        # Reserve before network activity so interruptions cannot evade the cap.
        with self.path.open("a") as stream:
            stream.write(json.dumps(record) + "\n")
        started = time.monotonic()
        try:
            response = self.client.generate(self.Request(
                model=self.model,
                messages=[self.Message("system", system), self.Message("user", content)],
                max_tokens=max_tokens, temperature=0.0, json_mode=False, extra=self.extra))
            result = {"attempt": calls + 1, "model": self.model, "status": "ok",
                      "text": response.text, "usage": asdict(response.usage),
                      "latency_ms": response.latency_ms, "cost_rmb": None,
                      "finish_reason": response.raw.get("choices", [{}])[0].get("finish_reason")}
            result["resolved_model"] = response.raw.get("model")
            result["usage_details"] = response.raw.get("usage", {})
            if not response.text or not response.text.strip():
                result.update(status="error", error="empty final content", error_type="EmptyModelOutput")
            elif result["finish_reason"] == "length":
                result.update(status="error", error="truncated final content", error_type="TruncatedModelOutput")
        except Exception as exc:
            # Never include response/request headers in logs or errors.
            result = {"attempt": calls + 1, "model": self.model, "status": "error",
                      "error_type": type(exc).__name__, "error": str(exc).replace(credentials(), "[REDACTED]"),
                      "latency_ms": (time.monotonic() - started) * 1000, "cost_rmb": None}
        self.path.with_name(f"{self.path.stem}_{calls + 1:03}.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False))
        if result["status"] == "error":
            raise ModelAPIError(result["error"])
        return result

    @property
    def calls_used(self):
        return len(self.path.read_text().splitlines()) if self.path.exists() else 0


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--smoke-result", required=True)
    parser.add_argument("--log", required=True)
    args = parser.parse_args()
    smoke_path = Path(args.smoke_result)
    task = json.loads(smoke_path.read_text())["task"]
    result = ModelAPI(args.model, args.log, max_calls=2).generate(
        "You are a navigation vision evidence investigator. Only use visible evidence. "
        "Do not claim navigation success or infer unseen rooms. Return JSON with keys "
        "visible_landmarks (list), next_visual_question (string), uncertainty (string).",
        json.dumps({"instruction": task["instruction"], "question": "Describe the initial scene and identify the first instruction landmark, if visible."}),
        images=[smoke_path.parent / "initial.png"], max_tokens=512)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
