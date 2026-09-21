#!/usr/bin/env python3
"""Generate the PDEUE function maturity and connector matrix.

The audit is deliberately based on Python's AST rather than importing application
modules, so it is safe to run without credentials or optional runtime services.
Tests are inspected as caller evidence, but are not themselves product symbols.
"""

from __future__ import annotations

import argparse
import ast
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


PRODUCT_AREAS = ("alembic", "app", "scripts")
STUB_MARKERS = ("todo", "fixme")
MOCK_NAMES = ("mock", "fake", "synthetic", "dummy")
ENTRY_DECORATORS = {"get", "post", "put", "patch", "delete", "websocket", "event"}


@dataclass
class Symbol:
    path: Path
    qualified_name: str
    short_name: str
    node: ast.FunctionDef | ast.AsyncFunctionDef
    class_name: str | None = None
    callers: set[str] = field(default_factory=set)
    outgoing: set[str] = field(default_factory=set)
    drifts: set[str] = field(default_factory=set)
    externally_invoked: bool = False

    @property
    def signature(self) -> tuple[set[str], bool]:
        args = self.node.args
        names = {arg.arg for arg in (*args.posonlyargs, *args.args, *args.kwonlyargs)}
        names.discard("self")
        names.discard("cls")
        return names, args.kwarg is not None


def python_files(root: Path) -> list[Path]:
    """Return product Python files; tests remain caller-only evidence."""
    files: list[Path] = []
    for area in PRODUCT_AREAS:
        base = root / area
        if base.exists():
            files.extend(base.rglob("*.py"))
    return sorted(set(files))


def all_python_files(root: Path) -> list[Path]:
    return sorted(root.rglob("*.py"))


def dotted_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = dotted_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return None


def decorator_leaf(node: ast.AST) -> str:
    if isinstance(node, ast.Call):
        node = node.func
    return (dotted_name(node) or "").rsplit(".", 1)[-1]


def iter_symbols(path: Path, tree: ast.Module, root: Path) -> Iterable[Symbol]:
    module = path.relative_to(root).with_suffix("").as_posix().replace("/", ".")
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield Symbol(path, f"{module}.{node.name}", node.name, node,
                         externally_invoked=any(decorator_leaf(d) in ENTRY_DECORATORS for d in node.decorator_list))
        elif isinstance(node, ast.ClassDef):
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    yield Symbol(path, f"{module}.{node.name}.{child.name}", child.name, child,
                                 class_name=node.name,
                                 externally_invoked=any(decorator_leaf(d) in ENTRY_DECORATORS for d in child.decorator_list))


def is_stub(symbol: Symbol, source: str) -> bool:
    body = symbol.node.body
    effective = body[1:] if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str) else body
    if not effective or all(isinstance(stmt, ast.Pass) or (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) and stmt.value.value is Ellipsis) for stmt in effective):
        return True
    if any(isinstance(n, ast.Raise) and isinstance(n.exc, ast.Call) and dotted_name(n.exc.func) == "NotImplementedError"
           for n in ast.walk(symbol.node)):
        return True
    segment = ast.get_source_segment(source, symbol.node) or ""
    # Marker words embedded in user-facing strings are not implementation
    # notes. Restrict marker matching to comments.
    comments = "\n".join(line.split("#", 1)[1] for line in segment.splitlines() if "#" in line)
    return any(marker in comments.lower() for marker in STUB_MARKERS)


def is_synthetic(symbol: Symbol) -> bool:
    """Detect explicitly fake implementations, not ordinary constant accessors."""
    synthetic_context = f"{symbol.path.stem} {symbol.class_name or ''}".lower()
    if any(part in synthetic_context for part in MOCK_NAMES):
        return True
    for node in ast.walk(symbol.node):
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):
            names = " ".join(n.id.lower() for n in ast.walk(node) if isinstance(n, ast.Name))
            if any(token in names for token in ("time", "timer", "tick", "counter")):
                return True
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            value = node.value
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            target_names = {n.id.lower() for target in targets for n in ast.walk(target) if isinstance(n, ast.Name)}
            if len(target_names & {"posted", "filled", "expired"}) >= 2 and isinstance(value, (ast.Tuple, ast.List)):
                if all(isinstance(elt, ast.Constant) for elt in value.elts):
                    return True
    return False


def enclosing_label(path: Path, tree: ast.Module, call: ast.Call, root: Path) -> str:
    best: ast.AST | None = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and hasattr(call, "lineno"):
            if node.lineno <= call.lineno <= getattr(node, "end_lineno", node.lineno):
                if best is None or node.lineno >= getattr(best, "lineno", 0):
                    best = node
    rel = f"backend/{path.relative_to(root).as_posix()}"
    return f"{rel}:{getattr(best, 'name', '<module>')}:{call.lineno}"


def audit(root: Path) -> tuple[list[Symbol], dict[Path, list[str]], list[str]]:
    parse_errors: list[str] = []
    trees: dict[Path, ast.Module] = {}
    sources: dict[Path, str] = {}
    for path in all_python_files(root):
        try:
            # utf-8-sig accepts ordinary UTF-8 while stripping legacy BOMs.
            sources[path] = path.read_text(encoding="utf-8-sig")
            trees[path] = ast.parse(sources[path], filename=str(path))
        except (OSError, SyntaxError, UnicodeError) as exc:
            parse_errors.append(f"backend/{path.relative_to(root)}: {exc}")

    symbols = [s for path in python_files(root) if path in trees for s in iter_symbols(path, trees[path], root)]
    by_leaf: dict[str, list[Symbol]] = defaultdict(list)
    classes: dict[Path, list[str]] = defaultdict(list)
    for symbol in symbols:
        by_leaf[symbol.short_name].append(symbol)
        # Calling a class invokes its constructor; indexing ``ClassName`` to
        # ``__init__`` captures those otherwise invisible connector edges.
        if symbol.short_name == "__init__" and symbol.class_name:
            by_leaf[symbol.class_name].append(symbol)
    for path in python_files(root):
        if path not in trees:
            continue
        for node in ast.walk(trees[path]):
            if isinstance(node, ast.ClassDef):
                classes[path].append(node.name)

    # A conservative name/attribute resolver. Ambiguous leaves are listed as all
    # plausible edges rather than silently inventing a single target.
    for path, tree in trees.items():
        for call in (n for n in ast.walk(tree) if isinstance(n, ast.Call)):
            called = dotted_name(call.func)
            if not called:
                continue
            leaf = called.rsplit(".", 1)[-1]
            targets = by_leaf.get(leaf, [])
            caller = enclosing_label(path, tree, call, root)
            for target in targets:
                target.callers.add(caller)
                target.outgoing  # ensure deterministic materialization
                accepted, has_kwargs = target.signature
                unknown = sorted(kw.arg for kw in call.keywords if kw.arg and kw.arg not in accepted and not has_kwargs)
                # A shared method leaf (for example, several ``record_fill``
                # methods) cannot be disambiguated safely without runtime type
                # information. Never report speculative signature drift.
                if unknown and len(targets) == 1:
                    target.drifts.add(f"{caller} passes {', '.join(f'`{x}`' for x in unknown)}")

        # Record outgoing calls on each product symbol.
        for symbol in (s for s in symbols if s.path == path):
            for call in (n for n in ast.walk(symbol.node) if isinstance(n, ast.Call)):
                name = dotted_name(call.func)
                if name:
                    symbol.outgoing.add(name)
    return symbols, classes, parse_errors


def maturity(symbol: Symbol, source: str) -> str:
    if is_stub(symbol, source):
        return "PARTIAL / STUB"
    if is_synthetic(symbol):
        return "SYNTHETIC MOCK"
    active = any(not caller.startswith("backend/tests/") for caller in symbol.callers)
    if not active and not symbol.externally_invoked:
        return "ORPHANED"
    return "COMPLETE"


def cell(items: Iterable[str], empty: str = "—") -> str:
    values = sorted(set(items))
    return "<br>".join(v.replace("|", "\\|") for v in values) if values else empty


def render(root: Path, symbols: list[Symbol], classes: dict[Path, list[str]], errors: list[str]) -> str:
    sources = {path: path.read_text(encoding="utf-8-sig") for path in python_files(root)}
    counts: dict[str, int] = defaultdict(int)
    rows: list[str] = []
    for symbol in sorted(symbols, key=lambda s: (str(s.path), s.node.lineno, s.qualified_name)):
        tag = maturity(symbol, sources[symbol.path])
        counts[tag] += 1
        callers = set(symbol.callers)
        if symbol.externally_invoked:
            callers.add("framework route/event dispatch")
        gaps: list[str] = []
        if symbol.drifts:
            gaps.append("**SIGNATURE DRIFT:** " + "; ".join(sorted(symbol.drifts)))
        if tag == "ORPHANED":
            gaps.append("No active caller found in production runtime entrypoints")
        if tag == "PARTIAL / STUB":
            gaps.append("Implementation placeholder must be completed")
        if tag == "SYNTHETIC MOCK":
            gaps.append("Replace synthetic behavior with a real downstream integration")
        gaps.append("Calls: " + cell(symbol.outgoing, "none"))
        rel = f"backend/{symbol.path.relative_to(root).as_posix()}"
        rows.append(f"| `{rel}` | `{symbol.qualified_name}` (L{symbol.node.lineno}) | **[{tag}]** | {cell(callers)} | {cell(gaps)} |")

    class_lines = []
    for path in sorted(classes):
        rel = f"backend/{path.relative_to(root).as_posix()}"
        for name in sorted(set(classes[path])):
            class_lines.append(f"| `{rel}` | `{name}` |")
    error_text = "\n".join(f"- `{e}`" for e in errors) or "- None."
    return f"""# PDEUE FUNCTION MATURITY & CONNECTOR MATRIX

Generated by `backend/scripts/function_maturity_audit.py`. Do not edit the matrix by hand.

## Audit scope and method

- Production inventory: every Python file under `backend/alembic`, `backend/app`, and `backend/scripts`.
- Caller analysis: every Python file under `backend`, including tests. A test-only caller does **not** prevent an `ORPHANED` classification.
- Connector matching is conservative static AST analysis by callable leaf name. Dynamic dispatch, dependency injection, and reflective calls may require human confirmation.
- Classification precedence is `PARTIAL / STUB`, `SYNTHETIC MOCK`, `ORPHANED`, then `COMPLETE`, so every function receives exactly one tag.

## Summary

| Tag | Count |
|---|---:|
| COMPLETE | {counts['COMPLETE']} |
| PARTIAL / STUB | {counts['PARTIAL / STUB']} |
| SYNTHETIC MOCK | {counts['SYNTHETIC MOCK']} |
| ORPHANED | {counts['ORPHANED']} |
| **Total functions / methods** | **{len(symbols)}** |
| **Classes** | **{sum(len(set(v)) for v in classes.values())}** |

## Parse errors

{error_text}

## Class inventory

| File Path | Class |
|---|---|
{chr(10).join(class_lines)}

## Connector matrix

| File Path | Function / Method | Maturity Tag | Callers / Upstream | Downstream Wiring Gap |
|---|---|---|---|---|
{chr(10).join(rows)}
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--check", action="store_true", help="fail if the committed report is stale")
    args = parser.parse_args()
    root = args.backend_root.resolve()
    output = args.output or root.parent / "docs" / "PDEUE_FUNCTION_MATURITY_CONNECTOR_MATRIX.md"
    symbols, classes, errors = audit(root)
    report = render(root, symbols, classes, errors)
    if args.check:
        if not output.exists() or output.read_text(encoding="utf-8") != report:
            print(f"stale audit report: {output}")
            return 1
        print(f"audit report is current: {len(symbols)} symbols")
        return 0
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report, encoding="utf-8")
    print(f"wrote {output} ({len(symbols)} symbols, {len(errors)} parse errors)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
