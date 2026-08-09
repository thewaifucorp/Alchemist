from __future__ import annotations
from copy import deepcopy
from typing import Any
from alchemist.core import Diagnostic, Result, Severity, new_ir, validate_ir

def _kind(raw: dict[str, Any]) -> str:
    data = raw.get("data", {}); text = " ".join(str(data.get(k, "")) for k in ("type", "display_name")) + " " + str(data.get("node", {}).get("display_name", "")); text = text.lower()
    for token, kind in (("chat input", "input"), ("chat output", "output"), ("prompt", "prompt"), ("language model", "llm"), ("openai", "llm"), ("agent", "agent"), ("memory", "memory"), ("retriever", "retriever"), ("conditional", "condition"), ("router", "router"), ("tool", "tool")):
        if token in text: return kind
    return "custom"

class LangFlowAdapter:
    framework = "langflow"
    def validate_source(self, source: dict[str, Any]) -> list[Diagnostic]:
        data = source.get("data") if isinstance(source, dict) else None
        if not isinstance(data, dict) or not isinstance(data.get("nodes"), list) or not isinstance(data.get("edges"), list):
            return [Diagnostic("INVALID_SOURCE_WORKFLOW", Severity.ERROR, "LangFlow workflow requires data.nodes[] and data.edges[]", framework=self.framework)]
        return []
    validate_target = validate_source

    def parse(self, source: dict[str, Any]) -> Result:
        diagnostics = self.validate_source(source)
        if diagnostics: return Result(None, diagnostics)
        ir = new_ir(str(source.get("name", "Untitled LangFlow workflow")))
        ir["extensions"]["langflow"] = {k: deepcopy(v) for k, v in source.items() if k not in {"name", "data"}}
        for i, raw in enumerate(source["data"]["nodes"]):
            node_id = str(raw.get("id", f"node-{i}")); kind = _kind(raw); data = raw.get("data", {}); template = data.get("node", {}).get("template", {})
            config = {k: deepcopy(v.get("value")) for k, v in template.items() if isinstance(v, dict) and "value" in v}
            ir["nodes"].append({"id": node_id, "kind": kind, "config": config, "inputs": [], "outputs": [], "metadata": {"name": data.get("node", {}).get("display_name") or data.get("display_name") or node_id}, "extensions": {"langflow": deepcopy(raw)}})
            if kind == "custom": diagnostics.append(Diagnostic("UNSUPPORTED_NODE_TYPE", Severity.WARNING, "Preserved unsupported LangFlow component", f"/data/nodes/{i}", self.framework))
        ids = {n["id"] for n in ir["nodes"]}
        for i, raw in enumerate(source["data"]["edges"]):
            start, end = raw.get("source"), raw.get("target")
            if start not in ids or end not in ids:
                diagnostics.append(Diagnostic("DROPPED_METADATA", Severity.WARNING, "Dropped edge with unknown endpoint", f"/data/edges/{i}", self.framework)); continue
            ir["edges"].append({"from": start, "to": end, "mapping": {"source_handle": raw.get("sourceHandle"), "target_handle": raw.get("targetHandle")}, "extensions": {"langflow": deepcopy(raw)}})
        return Result(ir, diagnostics + validate_ir(ir))

    def generate(self, ir: dict[str, Any]) -> Result:
        diagnostics = validate_ir(ir)
        if any(d.severity == Severity.ERROR for d in diagnostics): return Result(None, diagnostics)
        nodes = []
        for i, node in enumerate(ir["nodes"]):
            preserved = node.get("extensions", {}).get("langflow")
            if preserved: raw = deepcopy(preserved)
            else:
                component = {"input": "ChatInput", "output": "ChatOutput", "prompt": "Prompt", "llm": "LanguageModel", "agent": "Agent", "tool": "Tool", "memory": "Memory", "retriever": "Retriever", "condition": "ConditionalRouter"}.get(node["kind"], "CustomComponent")
                raw = {"id": node["id"], "type": "genericNode", "position": {"x": i * 280, "y": 0}, "data": {"type": component, "node": {"display_name": node.get("metadata", {}).get("name", component), "template": {k: {"value": v} for k, v in node.get("config", {}).items()}}}}
                diagnostics.append(Diagnostic("SEMANTIC_APPROXIMATION", Severity.WARNING, f"Synthesized LangFlow {component} component", framework=self.framework))
            raw["id"] = node["id"]; nodes.append(raw)
        edges = []
        for i, edge in enumerate(ir["edges"]):
            preserved = edge.get("extensions", {}).get("langflow")
            raw = deepcopy(preserved) if preserved else {"id": f"alchemist-edge-{i}", "source": edge["from"], "target": edge["to"], "sourceHandle": edge.get("mapping", {}).get("source_handle"), "targetHandle": edge.get("mapping", {}).get("target_handle")}
            raw.update({"source": edge["from"], "target": edge["to"]}); edges.append(raw)
        top = deepcopy(ir.get("extensions", {}).get("langflow", {})); top.update({"name": ir.get("metadata", {}).get("name", "Alchemist workflow"), "data": {"nodes": nodes, "edges": edges}})
        return Result(top, diagnostics)
