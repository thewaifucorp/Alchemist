from __future__ import annotations
from copy import deepcopy
from typing import Any
from alchemist.core import Diagnostic, Result, Severity, new_ir, validate_ir

KINDS = {"start": "input", "manualtrigger": "input", "webhook": "input", "httprequest": "tool", "if": "condition", "switch": "router", "set": "transform", "code": "transform", "function": "transform", "chatopenai": "llm", "lmchatopenai": "llm", "executeworkflow": "subflow"}

def _kind(type_name: str) -> str:
    leaf = type_name.rsplit(".", 1)[-1].lower()
    return next((kind for token, kind in KINDS.items() if token == leaf), "custom")

class N8nAdapter:
    framework = "n8n"
    def validate_source(self, source: dict[str, Any]) -> list[Diagnostic]:
        if not isinstance(source, dict) or not isinstance(source.get("nodes"), list) or not isinstance(source.get("connections", {}), dict):
            return [Diagnostic("INVALID_SOURCE_WORKFLOW", Severity.ERROR, "n8n workflow requires nodes[] and connections{}", framework=self.framework)]
        return []
    validate_target = validate_source

    def parse(self, source: dict[str, Any]) -> Result:
        diagnostics = self.validate_source(source)
        if diagnostics: return Result(None, diagnostics)
        ir = new_ir(str(source.get("name", "Untitled n8n workflow")))
        ir["extensions"]["n8n"] = {k: deepcopy(v) for k, v in source.items() if k not in {"name", "nodes", "connections"}}
        names: dict[str, str] = {}
        for i, raw in enumerate(source["nodes"]):
            node_id = str(raw.get("id") or raw.get("name") or f"node-{i}")
            names[str(raw.get("name", node_id))] = node_id
            kind = _kind(str(raw.get("type", "")))
            ir["nodes"].append({"id": node_id, "kind": kind, "config": deepcopy(raw.get("parameters", {})), "inputs": [], "outputs": [], "metadata": {"name": raw.get("name", node_id)}, "extensions": {"n8n": {k: deepcopy(v) for k, v in raw.items() if k not in {"id", "name", "parameters"}}}})
            if kind == "custom": diagnostics.append(Diagnostic("UNSUPPORTED_NODE_TYPE", Severity.WARNING, f"Preserved unsupported n8n node {raw.get('type')}", f"/nodes/{i}", self.framework))
        for source_name, groups in source.get("connections", {}).items():
            for channel, lanes in groups.items():
                for output_index, links in enumerate(lanes):
                    for link in links:
                        if source_name not in names or str(link.get("node")) not in names: continue
                        edge = {"from": names[source_name], "to": names[str(link["node"])], "mapping": {"source_channel": channel, "source_output": output_index, "target_input": link.get("index", 0)}}
                        ir["edges"].append(edge)
        return Result(ir, diagnostics + validate_ir(ir))

    def generate(self, ir: dict[str, Any]) -> Result:
        diagnostics = validate_ir(ir)
        if any(d.severity == Severity.ERROR for d in diagnostics): return Result(None, diagnostics)
        nodes, id_to_name = [], {}
        reverse = {v: k for k, v in KINDS.items()}
        defaults = {"input": "manualTrigger", "tool": "httpRequest", "condition": "if", "router": "switch", "transform": "set", "llm": "@n8n/n8n-nodes-langchain.lmChatOpenAi", "subflow": "executeWorkflow"}
        for node in ir["nodes"]:
            ext = deepcopy(node.get("extensions", {}).get("n8n", {})); name = str(node.get("metadata", {}).get("name", node["id"])); id_to_name[node["id"]] = name
            type_name = ext.pop("type", None) or "n8n-nodes-base." + defaults.get(node["kind"], "noOp")
            if node["kind"] in {"prompt", "agent", "memory", "retriever", "human_input", "output", "custom"} and "type" not in node.get("extensions", {}).get("n8n", {}):
                diagnostics.append(Diagnostic("SEMANTIC_APPROXIMATION", Severity.WARNING, f"Generated n8n noOp for {node['kind']} node", framework=self.framework))
            nodes.append({"parameters": deepcopy(node.get("config", {})), "id": node["id"], "name": name, "type": type_name, "typeVersion": ext.pop("typeVersion", 1), "position": ext.pop("position", [0, len(nodes) * 160]), **ext})
        connections: dict[str, Any] = {}
        for edge in ir["edges"]:
            mapping = edge.get("mapping", {}); channel = mapping.get("source_channel", "main"); output = int(mapping.get("source_output", 0))
            lanes = connections.setdefault(id_to_name[edge["from"]], {}).setdefault(channel, [])
            while len(lanes) <= output: lanes.append([])
            lanes[output].append({"node": id_to_name[edge["to"]], "type": channel, "index": int(mapping.get("target_input", 0))})
        top = deepcopy(ir.get("extensions", {}).get("n8n", {})); top.update({"name": ir.get("metadata", {}).get("name", "Alchemist workflow"), "nodes": nodes, "connections": connections})
        return Result(top, diagnostics)
