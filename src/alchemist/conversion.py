from __future__ import annotations
from typing import TYPE_CHECKING, Any
from alchemist.adapters import ADAPTERS
from alchemist.core import Result, validate_ir

if TYPE_CHECKING: from alchemist.semantic import SemanticMapper

def convert(source: dict[str, Any], source_format: str, target_format: str, semantic_mapper: SemanticMapper | None = None) -> Result:
    parsed = Result(source, validate_ir(source)) if source_format == "ir" else ADAPTERS[source_format].parse(source)
    if semantic_mapper is not None: parsed = semantic_mapper.apply(parsed)
    if not parsed.ok or target_format == "ir": return parsed
    generated = ADAPTERS[target_format].generate(parsed.value)
    generated.diagnostics = parsed.diagnostics + generated.diagnostics
    return generated
