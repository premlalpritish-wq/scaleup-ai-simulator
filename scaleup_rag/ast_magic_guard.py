import ast
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Union

ALLOWED_CONSTANTS: Set[Union[int, float]] = {0, 1, -1, 2, 0.0, 1.0, -1.0, 2.0}
ALLOWED_TABLE_NAMES: Set[str] = {
    "ALLOWED_CONSTANTS",
    "UNIT_CONVERSIONS",
    "DEFAULT_THRESHOLDS",
    "KELVIN_OFFSET_C",
}


class _MagicNumberVisitor(ast.NodeVisitor):
    def __init__(
        self,
        file_path: str,
        target_functions: Optional[Set[str]] = None,
    ):
        self.file_path = file_path
        self.target_functions = target_functions
        self.current_function: Optional[str] = None
        self.violations: List[Dict[str, Any]] = []
        self._skip_nodes: Set[int] = set()

    def _in_scope(self) -> bool:
        if self.target_functions is None:
            return True
        return self.current_function in self.target_functions

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        prev = self.current_function
        self.current_function = node.name
        # Skip default argument values in function signatures (schema/parameter defaults)
        for d in node.args.defaults + node.args.kw_defaults:
            if d is not None:
                self._mark_skip_subtree(d)
        self.generic_visit(node)
        self.current_function = prev

    visit_AsyncFunctionDef = visit_FunctionDef

    def _mark_skip_subtree(self, node: ast.AST) -> None:
        for child in ast.walk(node):
            self._skip_nodes.add(id(child))

    def visit_Assign(self, node: ast.Assign) -> None:
        # Allow explicitly annotated constant tables (ALLOWED_CONSTANTS, UNIT_CONVERSIONS, DEFAULT_THRESHOLDS)
        for tgt in node.targets:
            if isinstance(tgt, ast.Name) and tgt.id in ALLOWED_TABLE_NAMES:
                return
            if isinstance(tgt, ast.Attribute) and tgt.attr in ALLOWED_TABLE_NAMES:
                return
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if isinstance(node.target, ast.Name) and node.target.id in ALLOWED_TABLE_NAMES:
            return
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        # Allow round(x, ndigits) precision argument and range(n)
        if isinstance(node.func, ast.Name) and node.func.id == "round" and len(node.args) >= 2:
            self._mark_skip_subtree(node.args[1])
        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        # Allow constant integer indexing like arr[0], arr[-1], arr[2]
        self._mark_skip_subtree(node.slice)
        self.generic_visit(node)

    def visit_UnaryOp(self, node: ast.UnaryOp) -> None:
        if isinstance(node.op, (ast.USub, ast.UAdd)) and isinstance(node.operand, ast.Constant):
            val = node.operand.value
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                signed_val = -val if isinstance(node.op, ast.USub) else val
                if signed_val in ALLOWED_CONSTANTS:
                    self._skip_nodes.add(id(node.operand))
                    return
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        if id(node) in self._skip_nodes or not self._in_scope():
            return
        val = node.value
        if isinstance(val, bool):
            return
        if isinstance(val, (int, float)) and val not in ALLOWED_CONSTANTS:
            self.violations.append({
                "file": self.file_path,
                "line": node.lineno,
                "col": node.col_offset,
                "value": val,
                "function": self.current_function or "<module>",
            })


def lint_solver_magic_numbers(
    target_paths: Iterable[Union[str, Path]],
    function_names: Optional[Iterable[str]] = None,
) -> List[Dict[str, Any]]:
    """Scan Python solver files for bare numeric literals outside allowed constant tables."""
    target_funcs = set(function_names) if function_names is not None else None
    all_violations: List[Dict[str, Any]] = []
    for raw_path in target_paths:
        p = Path(raw_path)
        source = p.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(p))
        visitor = _MagicNumberVisitor(str(p), target_functions=target_funcs)
        visitor.visit(tree)
        all_violations.extend(visitor.violations)
    return all_violations


def assert_no_magic_numbers(
    target_paths: Iterable[Union[str, Path]],
    function_names: Optional[Iterable[str]] = None,
) -> None:
    violations = lint_solver_magic_numbers(target_paths, function_names=function_names)
    if violations:
        details = "; ".join(
            f"{v['file']}:{v['line']} in {v['function']}() -> {v['value']}"
            for v in violations[:10]
        )
        raise AssertionError(f"AST Magic Number Guard detected {len(violations)} bare literal(s): {details}")
