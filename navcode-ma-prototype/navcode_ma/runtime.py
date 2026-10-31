"""Trusted-fixture-only executable Python Policy runtime.

Security limit: AST checks + disabled builtins do NOT sandbox untrusted Python.
This demo ONLY runs two code sources whose SHA256 hashes are explicitly
allowlisted. Use an OS-isolated process/container with capability IPC for any
actual model-generated code; never relax this allowlist in production.
"""
import ast
import hashlib
from .policy_templates import FIRST_POLICY, REPAIR_POLICY

ALLOWED_HASHES = {hashlib.sha256(x.encode()).hexdigest() for x in
                  (FIRST_POLICY, REPAIR_POLICY)}
ALLOWED_NAV_METHODS = {"observe", "perceive", "step", "stop", "checkpoint"}
BLOCKED_NODES = (ast.Import, ast.ImportFrom, ast.ClassDef, ast.Lambda,
                 ast.Global, ast.Nonlocal, ast.With, ast.AsyncWith, ast.Try,
                 ast.Raise, ast.Delete, ast.Yield, ast.YieldFrom, ast.Await)


class UntrustedPolicyError(ValueError):
    pass


class TrustedFixtureRuntime:
    """Not a sandbox. Reproducible prototype only."""
    def validate(self, source: str) -> None:
        if hashlib.sha256(source.encode()).hexdigest() not in ALLOWED_HASHES:
            raise UntrustedPolicyError("Only reviewed fixture code may be executed")
        tree = ast.parse(source)
        if len(tree.body) != 1 or not isinstance(tree.body[0], ast.FunctionDef):
            raise UntrustedPolicyError("Expected one run() function")
        if tree.body[0].name != "run":
            raise UntrustedPolicyError("Unexpected entrypoint")
        for node in ast.walk(tree):
            if isinstance(node, BLOCKED_NODES):
                raise UntrustedPolicyError(f"Forbidden syntax: {type(node).__name__}")
            if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
                raise UntrustedPolicyError("Private attributes are not allowed")
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if isinstance(node.func.value, ast.Name) and node.func.value.id == "nav":
                    if node.func.attr not in ALLOWED_NAV_METHODS:
                        raise UntrustedPolicyError("Unauthorized navigation tool")

    def execute(self, source: str, nav, state: dict, task) -> dict:
        self.validate(source)
        namespace: dict = {"__builtins__": {"len": len, "range": range}}
        exec(compile(source, "<reviewed-policy-fixture>", "exec"), namespace)
        return namespace["run"](nav, state, task)
