"""Fail-closed Linux bubblewrap runtime with a narrow JSON capability RPC.

No host home, benchmark, credentials, GPU device, or host network is mounted.
The trusted parent owns all action/vision capabilities and state checkpoints.
"""
from __future__ import annotations

import json
import os
import selectors
import shutil
import subprocess
import time
from pathlib import Path


class PolicyRuntime:
    def __init__(self, timeout=60, max_requests=600):
        self.timeout = timeout
        self.max_requests = max_requests

    def run(self, source, state, handler):
        bwrap = shutil.which("bwrap")
        if bwrap is None:
            raise RuntimeError("bubblewrap required; in-process fallback is forbidden")
        worker = Path(__file__).with_name("policy_worker.py")
        cmd = [bwrap, "--unshare-all", "--die-with-parent", "--new-session", "--cap-drop", "ALL",
               "--clearenv", "--setenv", "PATH", "/usr/bin", "--setenv", "LANG", "C.UTF-8",
               "--ro-bind", "/usr/bin", "/usr/bin", "--ro-bind", "/usr/lib", "/usr/lib",
               "--ro-bind", "/lib", "/lib", "--ro-bind", "/lib64", "/lib64",
               "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
               "--ro-bind", str(worker), "/worker.py", "--chdir", "/tmp",
               "/usr/bin/python3", "-I", "-u", "/worker.py"]
        # No shell, and no inherited environment containing API credentials.
        process = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL, env={}, bufsize=0)
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ)
        buffer = b""
        requests = 0
        last_seq = 0
        deadline = time.monotonic() + self.timeout
        try:
            data = json.dumps({"source": source, "state": state}, allow_nan=False).encode() + b"\n"
            if len(data) > 65536:
                raise ValueError("source/state payload too large")
            process.stdin.write(data)
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not selector.select(max(0, remaining)):
                    raise TimeoutError("policy wall-time budget exhausted")
                part = os.read(process.stdout.fileno(), 65537)
                if not part:
                    raise RuntimeError(f"policy worker exited without result ({process.poll()})")
                buffer += part
                if len(buffer) > 65536:
                    raise ValueError("policy message too large")
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    msg = json.loads(line)
                    if msg.get("kind") == "done":
                        if not isinstance(msg.get("state"), dict):
                            raise ValueError("policy state must be a JSON object")
                        return msg["state"]
                    if msg.get("kind") == "exception":
                        raise RuntimeError(f"{msg.get('error_type')}: {msg.get('error')}")
                    requests += 1
                    if msg.get("kind") != "rpc" or requests > self.max_requests:
                        raise ValueError("invalid/excessive policy request")
                    if type(msg.get("seq")) is not int or msg["seq"] != last_seq + 1:
                        raise ValueError("invalid RPC sequence")
                    last_seq = msg["seq"]
                    if msg.get("method") not in ("observe", "perceive", "step", "checkpoint", "move_to_candidate", "turn", "recover"):
                        raise ValueError("unauthorized capability")
                    if not isinstance(msg.get("params"), dict):
                        raise ValueError("invalid parameters")
                    response = handler(msg["method"], msg["params"])
                    if time.monotonic() >= deadline:
                        raise TimeoutError("policy wall-time budget exhausted during tool call")
                    process.stdin.write(json.dumps({"seq": msg["seq"], "result": response},
                                                   allow_nan=False).encode() + b"\n")
        finally:
            selector.close()
            process.kill()
            process.wait(timeout=5)
            process.stdin.close()
            process.stdout.close()
