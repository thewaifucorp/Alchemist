from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol

IR_VERSION = "0.1.0"
NODE_KINDS = {"input", "output", "llm", "prompt", "tool", "agent", "router", "condition", "transform", "memory", "retriever", "human_input", "subflow", "custom"}

class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"

@dataclass(frozen=True)
class Diagnostic:
    code: str
    severity: Severity
    message: str
    path: str | None = None
    framework: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {k: v.value if isinstance(v, Enum) else v for k, v in self.__dict__.items() if v not in (None, {})}

@dataclass
class Result:
    value: dict[str, Any] | None
    diagnostics: list[Diagnostic] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.value is not None and not any(d.severity == Severity.ERROR for d in self.diagnostics)

class Adapter(Protocol):
    framework: str
    def parse(self, source: dict[str, Any]) -> Result: ...
    def generate(self, ir: dict[str, Any]) -> Result: ...
    def validate_source(self, source: dict[str, Any]) -> list[Diagnostic]: ...
    def validate_target(self, target: dict[str, Any]) -> list[Diagnostic]: ...

def new_ir(name: str = "Untitled") -> dict[str, Any]:
    return {"alchemist_ir_version": IR_VERSION, "metadata": {"name": name}, "inputs": [], "outputs": [], "variables": {}, "secrets": [], "nodes": [], "edges": [], "extensions": {}}

def validate_ir(ir: Any) -> list[Diagnostic]:
    errors: list[Diagnostic] = []
    if not isinstance(ir, dict):
        return [Diagnostic("INVALID_IR", Severity.ERROR, "IR must be a JSON object", framework="ir")]
    if ir.get("alchemist_ir_version") != IR_VERSION:
        errors.append(Diagnostic("UNSUPPORTED_IR_VERSION", Severity.ERROR, f"Expected IR version {IR_VERSION}", "/alchemist_ir_version", "ir"))
    for key, kind in (("nodes", list), ("edges", list), ("metadata", dict), ("extensions", dict)):
        if not isinstance(ir.get(key), kind):
            errors.append(Diagnostic("INVALID_IR", Severity.ERROR, f"{key} must be {kind.__name__}", f"/{key}", "ir"))
    nodes = ir.get("nodes", []) if isinstance(ir.get("nodes"), list) else []
    ids: set[str] = set()
    for index, node in enumerate(nodes):
        path = f"/nodes/{index}"
        if not isinstance(node, dict) or not isinstance(node.get("id"), str) or not node.get("id"):
            errors.append(Diagnostic("INVALID_IR", Severity.ERROR, "Node id must be a non-empty string", path + "/id", "ir")); continue
        if node["id"] in ids:
            errors.append(Diagnostic("DUPLICATE_NODE_ID", Severity.ERROR, f"Duplicate node id: {node['id']}", path + "/id", "ir"))
        ids.add(node["id"])
        if node.get("kind") not in NODE_KINDS:
            errors.append(Diagnostic("INVALID_NODE_KIND", Severity.ERROR, f"Unknown node kind: {node.get('kind')}", path + "/kind", "ir"))
    for index, edge in enumerate(ir.get("edges", []) if isinstance(ir.get("edges"), list) else []):
        for endpoint in ("from", "to"):
            if not isinstance(edge, dict) or edge.get(endpoint) not in ids:
                errors.append(Diagnostic("DANGLING_EDGE", Severity.ERROR, f"Edge {endpoint} does not reference a node", f"/edges/{index}/{endpoint}", "ir"))
    return errors
