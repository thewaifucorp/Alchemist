from typing import Any
from alchemist.adapters import ADAPTERS
from alchemist.core import Result, validate_ir

def convert(source: dict[str, Any], source_format: str, target_format: str) -> Result:
    parsed = Result(source, validate_ir(source)) if source_format == "ir" else ADAPTERS[source_format].parse(source)
    if not parsed.ok or target_format == "ir": return parsed
    generated = ADAPTERS[target_format].generate(parsed.value)
    generated.diagnostics = parsed.diagnostics + generated.diagnostics
    return generated
