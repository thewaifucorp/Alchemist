# Alchemist

Alchemist is an experimental, open-source compiler/transpiler for bidirectional conversion of agent and workflow definitions. It does not execute flows, build agents, provide a visual editor, or act as an orchestration runtime/workflow engine.

```text
Source framework → adapter → Alchemist IR → adapter → target framework
```

Alchemist IR 0.1.0 is a versioned, framework-agnostic graph format. Deterministic rules run first; unsupported semantics are preserved in vendor extensions where possible and always surfaced as diagnostics. The default pipeline uses no LLM; an optional LLM-assisted `SemanticMapper` can classify nodes the rules leave as `custom` (see below).

| Adapter | Parse to IR | Generate from IR | Status |
|---|---:|---:|---|
| n8n | yes (subset) | yes (subset) | experimental |
| LangFlow | yes (subset) | yes (subset) | experimental |
| LangGraph | no | no | planned |
| Bastion | no | no | planned |

## Install and use

```bash
python -m pip install -e .
alchemist inspect --from n8n workflow.json
alchemist convert --from n8n --to ir workflow.json
alchemist convert --from n8n --to langflow workflow.json -o flow.json
alchemist validate workflow.alchemist.json
python -m unittest discover -s tests -v
```

## Optional LLM-assisted mapping

Off by default. With `--semantic`, `inspect` and `convert` send only the nodes the deterministic rules left as `custom` to an OpenAI-compatible `/chat/completions` endpoint, which may propose their IR `kind` and `inputs`/`outputs` ports.

```bash
export ALCHEMIST_LLM_BASE_URL=http://localhost:11434/v1   # or --llm-base-url
export ALCHEMIST_LLM_MODEL=qwen2.5-coder                   # or --llm-model
export ALCHEMIST_LLM_API_KEY=...                           # optional; --llm-api-key-env renames the variable
alchemist convert --semantic --from n8n --to ir workflow.json
```

- Only node ids, names, config keys (never values) and vendor type hints are sent.
- Every proposal is validated against IR 0.1.0; invalid ones are rejected with `SEMANTIC_MAPPING_REJECTED`.
- Accepted mappings emit `SEMANTIC_APPROXIMATION` and record provenance in `extensions.alchemist` (`"source": "llm"` vs `"rule"`).
- Endpoint or reply errors keep the deterministic result and emit `SEMANTIC_MAPPER_UNAVAILABLE`.

`--llm-timeout` / `ALCHEMIST_LLM_TIMEOUT` sets the request timeout (default 60 s). See [ADR 0002](docs/adr/0002-optional-llm-semantic-mapper.md).

The initial adapters recognize common trigger/input, HTTP tool, condition/router, transform, model, prompt, agent, memory, retriever, output, and subflow concepts. Generated cross-framework components are deliberately minimal and may require target-side configuration. See `docs/research`, [ADR 0001](docs/adr/0001-alchemist-ir.md) and [ADR 0002](docs/adr/0002-optional-llm-semantic-mapper.md).

## Contributing

Add universal concepts only with evidence from multiple frameworks. Keep framework code inside adapters, preserve unknown source data, and add fixtures plus diagnostics for every lossy mapping.

Licensed under Apache-2.0.
