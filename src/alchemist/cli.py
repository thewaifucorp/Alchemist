from __future__ import annotations
import argparse, json, sys
from pathlib import Path
from alchemist.adapters import ADAPTERS
from alchemist.conversion import convert
from alchemist.core import validate_ir

def _read(path: str) -> dict:
    with (sys.stdin if path == "-" else Path(path).open(encoding="utf-8")) as stream: return json.load(stream)

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="alchemist", description="Transpile workflows through Alchemist IR")
    sub = parser.add_subparsers(dest="command", required=True)
    inspect = sub.add_parser("inspect"); inspect.add_argument("file"); inspect.add_argument("--from", dest="source", choices=["ir", *ADAPTERS], required=True)
    conv = sub.add_parser("convert"); conv.add_argument("file"); conv.add_argument("--from", dest="source", choices=["ir", *ADAPTERS], required=True); conv.add_argument("--to", dest="target", choices=["ir", *ADAPTERS], required=True); conv.add_argument("-o", "--output")
    valid = sub.add_parser("validate"); valid.add_argument("file")
    args = parser.parse_args(argv)
    try: source = _read(args.file)
    except (OSError, json.JSONDecodeError) as exc: print(f"error: {exc}", file=sys.stderr); return 2
    if args.command == "validate": result, diagnostics = source, validate_ir(source)
    elif args.command == "inspect":
        converted = convert(source, args.source, "ir"); diagnostics = converted.diagnostics; result = {"valid": converted.ok, "nodes": len(converted.value.get("nodes", [])) if converted.value else 0, "edges": len(converted.value.get("edges", [])) if converted.value else 0, "diagnostics": [d.as_dict() for d in diagnostics]}
    else:
        converted = convert(source, args.source, args.target); result, diagnostics = converted.value, converted.diagnostics
    if args.command == "convert" and result is not None:
        text = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
        if args.output: Path(args.output).write_text(text, encoding="utf-8")
        else: print(text, end="")
    elif args.command != "convert": print(json.dumps(result if args.command == "inspect" else {"valid": not diagnostics, "diagnostics": [d.as_dict() for d in diagnostics]}, indent=2))
    for d in diagnostics:
        if args.command == "convert": print(json.dumps(d.as_dict()), file=sys.stderr)
    return 0 if result is not None and not any(d.severity.value == "error" for d in diagnostics) else 1

if __name__ == "__main__": raise SystemExit(main())
