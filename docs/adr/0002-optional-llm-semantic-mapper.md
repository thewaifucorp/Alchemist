# ADR 0002: Optional LLM-assisted SemanticMapper

- Status: Accepted
- Date: 2026-10-15
- Amends: [ADR 0001](0001-alchemist-ir.md) ("An optional future `SemanticMapper` may resolve genuine ambiguity")

## Context and problem

Deterministic rules classify the node types they know. Everything else becomes a `custom` node with an `UNSUPPORTED_NODE_TYPE` warning: the payload survives in `extensions.<framework>`, but the IR loses the node's meaning (a community "Slack send" node is semantically a `tool`). Alchemist is meant to be a static parser assisted by an LLM, so the gap ADR 0001 left open needs a concrete, safe shape.

## Decision

Implement `SemanticMapper` (`alchemist.semantic`) as an **opt-in** pass that runs after an adapter (or IR input) parses successfully. The deterministic pipeline stays the default and is byte-for-byte unchanged when the mapper is not configured.

- **Scope.** Only nodes the rules left as `custom` are sent. The LLM may propose `kind` (any IR kind) and `inputs`/`outputs` ports. It cannot touch `config`, edges, extensions, metadata or rule-resolved nodes. If rules resolve every node, no request is made.
- **Endpoint.** Any OpenAI-compatible `/chat/completions` endpoint, configured by `--llm-base-url`/`ALCHEMIST_LLM_BASE_URL`, `--llm-model`/`ALCHEMIST_LLM_MODEL`, an API key read from the environment (`ALCHEMIST_LLM_API_KEY` by default, renamable with `--llm-api-key-env`, optional for local endpoints) and `--llm-timeout`/`ALCHEMIST_LLM_TIMEOUT`. Standard library only, `temperature: 0`.
- **Minimal disclosure.** The prompt carries node id, display name, config **keys** (never values) and vendor type/name/description hints. The API key never appears in diagnostics or `repr`.
- **Validation.** Every proposal is checked against IR 0.1.0 (known kind, port shape `name`/`schema`/`required`, unique port names, existing unresolved node, no duplicates, no extra keys). Invalid proposals are rejected one by one with `SEMANTIC_MAPPING_REJECTED`; the node stays `custom`. The final IR is re-validated; if it were ever invalid, all mappings are discarded.
- **Provenance.** Accepted mappings emit `SEMANTIC_APPROXIMATION` (path, model, previous and new kind, changed fields) and set `extensions.alchemist.provenance = {"source": "llm", "model", "fields", "previous_kind", "rationale"?}` on the node. Rule-resolved nodes get `{"source": "rule"}` (existing provenance is kept on re-runs). The document gets `extensions.alchemist.semantic_mapper = {model, mapped, rejected}`.
- **Fallback.** Network errors, HTTP errors, timeouts, non-JSON or wrongly shaped replies return the deterministic IR unchanged plus one `SEMANTIC_MAPPER_UNAVAILABLE` warning. The LLM never turns a successful conversion into a failure.
- **Generation.** Target adapters still prefer preserved vendor payloads, so an LLM-mapped node goes back to its original framework with its original type; the mapped kind matters for cross-framework targets.

## Consequences

Conversions can carry meaning for unknown nodes without silently modifying a workflow: every intervention is optional, validated, diagnosed and attributed. Results with the mapper on are not reproducible across models or endpoints; the provenance records which model produced each mapping. Tests use fake clients and a patched transport, so CI needs no network or credentials. Mapping config fields onto canonical names is out of scope while IR 0.1.0 keeps `config` opaque.
