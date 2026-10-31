# NavCode-MA — Multi-Agent Code-as-Policies VLN (protocol prototype)

**Status: mock-only proof of protocol. It does NOT run Habitat, R2R-CE or RxR-CE, and does NOT call any real model.**

This prototype validates a narrow architectural claim: a Code Agent produces an executable Python policy; that policy carries state and performs multiple local actions; a Vision Agent investigates perception requests against a shared, episode-scoped evidence history; the Code Agent is recalled on a high-level failure event and patches the remaining program without replaying previous actions.

## Quick start

```bash
cd navcode-ma-prototype
python -m navcode_ma.demo --output runs/demo
python -m navcode_ma.demo --inject-uncertain-goal --output runs/repair_demo
python -m pytest -q
```

Python 3.10+; `pytest` is needed only for tests. No third-party dependency required for demo.

## What the files do

- `code_agent.py` — model-neutral CodeAgentBackend protocol + deterministic mock.
- `vision_agent.py` — bounded visual evidence investigation and mock semantic inference.
- `memory.py` — per-episode event store, history recall, revocable claim ledger.
- `runtime.py` — *trusted fixture only* Python code execution, with a strict SHA256 allowlist.
- `supervisor.py` — permissioned motion owner and perception / code-agent event routing.
- `mock_env.py` — tiny synthetic route with two doors and a left turn.
- `docs/NavCode_MA_Design_v1.2.md` — detailed research-aware design, interfaces, implementation roadmap.

## Security and benchmark honesty

- `runtime.py` uses `exec` **only for two trusted reviewed fixtures**. AST checks and restricted builtins are **not a sandbox**. Never remove the hash allowlist to run LLM-generated code. Real runtime needs an OS-isolated worker and capability-restricted RPC.
- Mock observations contain textual synthetic visual hints rather than RGB frames; they are **test fixtures, not ground-truth-safe VLN sensing**. A real adapter must only expose sensors allowed by the selected R2R-CE / RxR-CE track.
- The private `mock_success` field is an integration assertion, not a benchmark success metric. Neither Agent gets that result.
- Runtime in this prototype is synchronous and in-process. Real implementation must handle policy suspension, agent session concurrency, model timeouts and idempotent actions across process boundaries.
- Backend interfaces for real Codex/API and Habitat are intentionally *not implemented* until the new evaluation repository's real protocol is inspected.
