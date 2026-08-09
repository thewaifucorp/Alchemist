# n8n export format

Research baseline: n8n's official documentation and repository, reviewed 2026-08-09.

An exported workflow is a JSON object centered on `name`, `nodes`, `connections`, and `settings`. Nodes carry `id`, `name`, `type`, `typeVersion`, `position`, `parameters`, optional credentials, and execution/UI settings. `connections` is keyed by source node name, then channel (normally `main`), output index, and target descriptors (`node`, `type`, `index`). Expressions live inside parameter values and credentials are references rather than portable secrets.

Canonical candidates: node identity, broad operation kind, configuration, directed edges, branches, variables, and secret references. n8n-only data retained in extensions: exact type/version, canvas position, credentials, disabled/retry/error settings, pin data, workflow settings/tags/static data, port indices, and unknown node payloads.

Sources: [n8n workflow export/import](https://docs.n8n.io/workflows/export-import/), [workflow API example](https://docs.n8n.io/embed/managing-workflows/), [workflow packages](https://docs.n8n.io/workflows/export-import/n8n-packages/).
