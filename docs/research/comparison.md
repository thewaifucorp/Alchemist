# n8n and LangFlow comparison

| Concept | n8n | LangFlow | IR treatment |
|---|---|---|---|
| Graph node | integration/core node | typed component | `nodes[]` |
| Node behavior | `type` + `parameters` | component + template | `kind` + `config` |
| Connection | name/channel/index map | edge with typed handles | edge + optional mapping |
| Branching | output lanes of IF/Switch | conditional components/ports | condition/router plus edge condition |
| Credentials | credential references | global/secret fields | secret references; never secret values |
| Canvas/UI | position and notes | React Flow geometry/UI metadata | framework extension |
| Unknown component | arbitrary node package | custom component/code | `custom` + full extension + diagnostic |

The overlap supports a small graph IR, but neither framework's payload is a safe canonical form. n8n connections encode execution item channels; LangFlow handles encode type compatibility and component ports. Flattening either silently loses semantics. Therefore mapping fields are deliberately open in 0.1.0, exact source payloads are retained under extensions, and cross-framework synthesis reports approximation.
