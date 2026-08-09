# ADR 0001: Alchemist IR

- Status: Accepted
- Date: 2026-08-09
- Validated against: n8n and LangFlow export formats

## Context and problem

Alchemist must convert workflows bidirectionally without making any supported framework the architectural center. n8n uses execution-oriented named connection maps; LangFlow uses typed component graphs. Direct pairwise converters multiply quickly and encourage silent loss.

## Alternatives considered

We considered n8n JSON, LangFlow JSON, LangGraph code/state graphs, and Bastion's internal format as the canonical representation. Each imports vendor semantics and makes other adapters second-class. Pairwise conversion avoids a canonical model but grows quadratically and produces inconsistent diagnostics.

## Decision

Adopt a framework-agnostic, explicitly versioned Alchemist IR, beginning at `0.1.0`. It models flow metadata, interface ports, variables, secret references, semantic nodes, edges, and namespaced extensions. Core code imports no adapter. Adapters parse/generate IR and return diagnostics alongside values.

The IR prefers deterministic parsing, schema mapping, and rules. An optional future `SemanticMapper` may resolve genuine ambiguity, but is never required and every intervention must emit `SEMANTIC_APPROXIMATION` (or a more specific diagnostic). It cannot silently modify a workflow.

## Loss and extensions

Round-trip equivalence is semantic, not byte equality. Unsupported fields, dropped metadata, invalid constructs, and approximations are diagnostics. Exact framework payloads may be stored in `extensions.<framework>` to enable high-fidelity return without promoting them to universal concepts. Extensions must be JSON values and consumers must tolerate unknown namespaces.

Schema versions follow semantic versioning. Readers reject unsupported versions in the initial implementation. Future incompatible shapes require a new version and explicit migration rather than reinterpretation.

## Consequences

Adapters remain plug-in modules and cross-framework conversions share one path. Some configuration is intentionally opaque in 0.1.0. Preserving source envelopes increases document size, and generated targets may require user review. Evidence from both n8n and LangFlow supports the common graph model while demonstrating why connection/handle details belong in mappings or extensions.
