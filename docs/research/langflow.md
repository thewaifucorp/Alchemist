# LangFlow export format

Research baseline: LangFlow's official documentation and repository, reviewed 2026-08-09.

A flow export has top-level identity/description fields and `data.nodes` plus `data.edges`. The graph is React Flow-shaped. Nodes include canvas data and a rich component definition under `data.node`: component type/display information, typed outputs, and a `template` whose fields carry values plus UI/type metadata. Edges identify source/target and serialized typed handles.

Canonical candidates: node identity, semantic kind, configuration values, typed ports, and directed edges. LangFlow-only data retained in extensions: full component definitions/code, field UI metadata, handle encodings, canvas geometry, visual state, endpoint metadata, and top-level deployment/project fields.

Sources: [LangFlow import/export](https://docs.langflow.org/concepts-flows-import), [flow API](https://docs.langflow.org/api-flows), [official starter flows](https://github.com/langflow-ai/langflow/tree/main/src/backend/base/langflow/initial_setup/starter_projects).
