"""JSON and Python policy protocol checks; the runtime provides isolation."""
import ast
import json

def parse_json(text):
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("model output must be a JSON object")
    return value

def validate_program(source):
    # A protocol check, NOT the security boundary (bubblewrap is that boundary).
    tree = ast.parse(source)
    run = next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "run"), None)
    if run is None:
        raise ValueError("policy must define run(nav, state)")
    if not any(isinstance(node, (ast.For, ast.While)) and any(
        isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute)
        and isinstance(child.func.value, ast.Name) and child.func.value.id == "nav"
        and child.func.attr == "perceive" for child in ast.walk(node))
        for node in ast.walk(run)):
        raise ValueError("policy must contain a long-lived decision loop with nav.perceive")
