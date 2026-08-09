# Alchemist

Alchemist is an experimental, open-source compiler/transpiler for bidirectional conversion of agent and workflow definitions. It does not execute flows, build agents, provide a visual editor, or act as an orchestration runtime/workflow engine.

```text
Source framework → adapter → Alchemist IR → adapter → target framework
```

Alchemist IR 0.1.0 is a versioned, framework-agnostic graph format. Deterministic rules run first; unsupported semantics are preserved in vendor extensions where possible and always surfaced as diagnostics. No LLM is used by the current pipeline.

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

The initial adapters recognize common trigger/input, HTTP tool, condition/router, transform, model, prompt, agent, memory, retriever, output, and subflow concepts. Generated cross-framework components are deliberately minimal and may require target-side configuration. See `docs/research` and [ADR 0001](docs/adr/0001-alchemist-ir.md).

## Contributing

Add universal concepts only with evidence from multiple frameworks. Keep framework code inside adapters, preserve unknown source data, and add fixtures plus diagnostics for every lossy mapping.

Licensed under Apache-2.0.
