"""Optional LLM-assisted semantic mapping for nodes the deterministic rules leave unresolved.

The mapper only runs when explicitly configured. It may change the ``kind``, ``inputs`` and
``outputs`` of nodes the adapters parsed as ``custom``; it never touches config, edges,
extensions or nodes already resolved by rules. Every proposal is validated against IR 0.1.0
and either applied with ``SEMANTIC_APPROXIMATION`` plus provenance, or rejected with a
diagnostic. Any endpoint or response failure falls back to the deterministic IR.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Protocol

from alchemist.core import NODE_KINDS, Diagnostic, Result, Severity, validate_ir

ENV_BASE_URL, ENV_MODEL, ENV_API_KEY, ENV_TIMEOUT = "ALCHEMIST_LLM_BASE_URL", "ALCHEMIST_LLM_MODEL", "ALCHEMIST_LLM_API_KEY", "ALCHEMIST_LLM_TIMEOUT"
MAPPABLE_KINDS = sorted(NODE_KINDS - {"custom"})
PROPOSAL_KEYS = {"id", "kind", "inputs", "outputs", "rationale"}
PORT_KEYS = {"name", "schema", "required"}
HINT_KEYS = {"type", "display_name", "description"}
MAX_HINT, MAX_RATIONALE = 200, 500

SYSTEM_PROMPT = f"""You map workflow nodes that deterministic rules could not classify into Alchemist IR 0.1.0.
For each node, choose exactly one kind from: {", ".join(MAPPABLE_KINDS)}. Use "custom" only when no kind fits.
Optionally declare its ports as lists of objects with "name" (string), optional "schema" (JSON Schema object)
and optional "required" (boolean). Do not invent nodes. Reply with JSON only, shaped as:
{{"nodes": [{{"id": "...", "kind": "...", "inputs": [...], "outputs": [...], "rationale": "one short sentence"}}]}}"""


class SemanticMapperError(Exception):
    """The LLM endpoint failed or answered something that is not a usable completion."""


class ChatClient(Protocol):
    def complete(self, messages: list[dict[str, str]]) -> str: ...


@dataclass(frozen=True)
class LLMConfig:
    """OpenAI-compatible endpoint settings. The API key is optional (local endpoints) and never printed."""

    base_url: str
    model: str
    api_key: str | None = field(default=None, repr=False)
    timeout: float = 60.0

    def __post_init__(self) -> None:
        if not re.match(r"^https?://[^/\s]+", self.base_url or ""):
            raise ValueError(f"LLM base URL must be an http(s) URL (flag --llm-base-url or {ENV_BASE_URL})")
        if not self.model:
            raise ValueError(f"LLM model is required (flag --llm-model or {ENV_MODEL})")
        if self.timeout <= 0:
            raise ValueError("LLM timeout must be positive")

    @classmethod
    def resolve(cls, base_url: str | None = None, model: str | None = None, api_key_env: str = ENV_API_KEY, timeout: float | None = None, environ: Mapping[str, str] | None = None) -> LLMConfig:
        """Build a config from explicit values, falling back to ``ALCHEMIST_LLM_*`` environment variables."""
        env = os.environ if environ is None else environ
        try:
            resolved_timeout = timeout if timeout is not None else float(env.get(ENV_TIMEOUT, "60"))
        except ValueError as exc:
            raise ValueError(f"{ENV_TIMEOUT} must be a number") from exc
        return cls(base_url or env.get(ENV_BASE_URL, ""), model or env.get(ENV_MODEL, ""), env.get(api_key_env) or None, resolved_timeout)


class OpenAICompatibleClient:
    """Minimal ``/chat/completions`` client using only the standard library."""

    def __init__(self, config: LLMConfig) -> None:
        self.config = config

    def complete(self, messages: list[dict[str, str]]) -> str:
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        body = json.dumps({"model": self.config.model, "messages": messages, "temperature": 0}).encode()
        request = urllib.request.Request(self.config.base_url.rstrip("/") + "/chat/completions", data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout) as response:
                payload = json.loads(response.read())
        except urllib.error.HTTPError as exc:
            raise SemanticMapperError(f"LLM endpoint returned HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise SemanticMapperError(f"LLM endpoint unreachable: {exc.reason}") from exc
        except (OSError, ValueError) as exc:
            raise SemanticMapperError(f"LLM endpoint failed: {exc.__class__.__name__}") from exc
        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise SemanticMapperError("LLM response has no choices[0].message.content") from exc
        if not isinstance(content, str):
            raise SemanticMapperError("LLM message content is not a string")
        return content


def _hints(value: Any, depth: int = 0) -> list[str]:
    """Collect short vendor type/name/description strings, never config values."""
    if depth > 4 or not isinstance(value, dict):
        return []
    found = []
    for key, item in value.items():
        if key in HINT_KEYS and isinstance(item, str) and item:
            found.append(f"{key}={item[:MAX_HINT]}")
        elif key != "template":
            found.extend(_hints(item, depth + 1))
    return found


def _parse_reply(text: str) -> list[Any]:
    fenced = re.fullmatch(r"\s*```(?:json)?\s*(.*?)\s*```\s*", text, re.DOTALL)
    try:
        reply = json.loads(fenced.group(1) if fenced else text)
    except ValueError as exc:
        raise SemanticMapperError("LLM reply is not JSON") from exc
    if not isinstance(reply, dict) or not isinstance(reply.get("nodes"), list):
        raise SemanticMapperError('LLM reply must be an object with a "nodes" array')
    nodes: list[Any] = reply["nodes"]
    return nodes


def _port_problem(ports: Any) -> str | None:
    if not isinstance(ports, list):
        return "ports must be an array"
    names = set()
    for port in ports:
        if not isinstance(port, dict) or set(port) - PORT_KEYS:
            return f"ports allow only {sorted(PORT_KEYS)}"
        if not isinstance(port.get("name"), str) or not port["name"] or port["name"] in names:
            return "port name must be a unique non-empty string"
        if "schema" in port and not isinstance(port["schema"], dict):
            return "port schema must be an object"
        if "required" in port and not isinstance(port["required"], bool):
            return "port required must be a boolean"
        names.add(port["name"])
    return None


def _proposal_problem(proposal: Any, unresolved: set[str], seen: set[str]) -> str | None:
    if not isinstance(proposal, dict) or set(proposal) - PROPOSAL_KEYS:
        return f"proposal allows only {sorted(PROPOSAL_KEYS)}"
    node_id = proposal.get("id")
    if not isinstance(node_id, str):
        return "id must be a string"
    if node_id in seen:
        return "duplicate proposal for node"
    if node_id not in unresolved:
        return "node does not exist or was already resolved by deterministic rules"
    if proposal.get("kind") not in NODE_KINDS:
        return f"kind must be one of {MAPPABLE_KINDS}"
    if "rationale" in proposal and not isinstance(proposal["rationale"], str):
        return "rationale must be a string"
    return next((problem for key in ("inputs", "outputs") if key in proposal and (problem := _port_problem(proposal[key]))), None)


class SemanticMapper:
    """Resolve ``custom`` nodes through an LLM, keeping every change validated, diagnosed and attributed."""

    def __init__(self, client: ChatClient, model: str) -> None:
        self.client, self.model = client, model

    @classmethod
    def from_config(cls, config: LLMConfig) -> SemanticMapper:
        return cls(OpenAICompatibleClient(config), config.model)

    def apply(self, parsed: Result) -> Result:
        """Return ``parsed`` enriched by LLM mappings, or unchanged plus a warning when the LLM cannot help."""
        ir = parsed.value
        if not parsed.ok or ir is None:
            return parsed
        positions = {node["id"]: i for i, node in enumerate(ir["nodes"]) if node["kind"] == "custom"}
        if not positions:
            return parsed
        request = [{"id": node_id, "name": ir["nodes"][i].get("metadata", {}).get("name"), "config_keys": sorted(ir["nodes"][i].get("config", {})), "vendor_hints": _hints(ir["nodes"][i].get("extensions", {}))} for node_id, i in positions.items()]
        messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": json.dumps({"nodes": request}, ensure_ascii=False)}]
        try:
            proposals = _parse_reply(self.client.complete(messages))
        except SemanticMapperError as exc:
            return Result(ir, parsed.diagnostics + [Diagnostic("SEMANTIC_MAPPER_UNAVAILABLE", Severity.WARNING, f"Kept deterministic mapping: {exc}", framework="semantic")])

        mapped_ir, diagnostics = deepcopy(ir), list(parsed.diagnostics)
        mapped: list[str] = []
        rejected: list[str] = []
        seen: set[str] = set()
        for proposal in proposals:
            problem = _proposal_problem(proposal, set(positions), seen)
            node_id: str | None = proposal.get("id") if isinstance(proposal, dict) and isinstance(proposal.get("id"), str) else None
            if problem or node_id is None:
                rejected.append(str(node_id))
                diagnostics.append(Diagnostic("SEMANTIC_MAPPING_REJECTED", Severity.WARNING, f"Rejected LLM mapping: {problem}", f"/nodes/{positions[node_id]}" if node_id in positions else None, "semantic", {"proposal": proposal}))
                continue
            seen.add(node_id)
            if proposal["kind"] == "custom":
                continue
            index = positions[node_id]
            node = mapped_ir["nodes"][index]
            fields = ["kind"] + [key for key in ("inputs", "outputs") if key in proposal]
            for key in fields:
                node[key] = deepcopy(proposal[key])
            provenance = {"source": "llm", "model": self.model, "fields": fields, "previous_kind": "custom"}
            if proposal.get("rationale"):
                provenance["rationale"] = proposal["rationale"][:MAX_RATIONALE]
            node.setdefault("extensions", {})["alchemist"] = {"provenance": provenance}
            mapped.append(node_id)
            diagnostics.append(Diagnostic("SEMANTIC_APPROXIMATION", Severity.WARNING, f"LLM mapped custom node to {proposal['kind']}", f"/nodes/{index}", "semantic", {"provenance": "llm", "model": self.model, "previous_kind": "custom", "kind": proposal["kind"], "fields": fields}))

        for node in mapped_ir["nodes"]:
            if node["kind"] != "custom" and node["id"] not in mapped:
                node.setdefault("extensions", {}).setdefault("alchemist", {"provenance": {"source": "rule"}})
        mapped_ir["extensions"]["alchemist"] = {"semantic_mapper": {"model": self.model, "mapped": mapped, "rejected": rejected}}
        errors = validate_ir(mapped_ir)
        if errors:  # defensive: per-proposal checks should make this unreachable
            return Result(ir, parsed.diagnostics + [Diagnostic("SEMANTIC_MAPPING_REJECTED", Severity.WARNING, "Rejected all LLM mappings: result is not valid IR", framework="semantic", details={"errors": [e.as_dict() for e in errors]})])
        return Result(mapped_ir, diagnostics)
