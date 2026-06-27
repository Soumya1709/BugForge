import ast
from typing import Optional
 
# ─────────────────────────────────────────────────────────────────────────────
# ACTION NAMES  (must match generate_dataset.py BUG_NAMES exactly)
# ─────────────────────────────────────────────────────────────────────────────
 
ACTION_NAMES = {
    0: "swap_comparison_operator",
    1: "off_by_one",
    2: "flip_boolean_return",
    3: "swap_variable_reference",
    4: "invert_conditional",
    5: "wrong_initial_value",
    6: "wrong_arithmetic_operator",
    7: "wrong_return_value",
}
 
# ─────────────────────────────────────────────────────────────────────────────
# SHARED BASE
# ─────────────────────────────────────────────────────────────────────────────
 
class _FixOnce:
    """
    Mixin for all fix transformers.
    Modifies exactly the FIRST matching AST node, then stops.
    Sets self.done = True and self.modified_line after a change.
    """
    def __init__(self):
        self.done = False
        self.modified_line: Optional[int] = None
 
 
# ─────────────────────────────────────────────────────────────────────────────
# ACTION 0 — Swap comparison operator  (self-inverse: flip twice = original)
# ─────────────────────────────────────────────────────────────────────────────
 
COMP_SWAPS = {
    ast.Lt: ast.Gt,   ast.Gt: ast.Lt,
    ast.LtE: ast.GtE, ast.GtE: ast.LtE,
    ast.Eq: ast.NotEq, ast.NotEq: ast.Eq,
}
 
class _FixSwapComparison(_FixOnce, ast.NodeTransformer):
    def __init__(self): _FixOnce.__init__(self)
    def visit_Compare(self, node):
        if not self.done:
            for i, op in enumerate(node.ops):
                if type(op) in COMP_SWAPS:
                    node.ops[i] = COMP_SWAPS[type(op)]()
                    self.done = True
                    self.modified_line = getattr(node, 'lineno', None)
                    break
        self.generic_visit(node)
        return node
 
 
# ─────────────────────────────────────────────────────────────────────────────
# ACTION 1 — Off-by-one fix  (injector subtracted 1; fix adds 1 back)
# ─────────────────────────────────────────────────────────────────────────────
 
class _FixOffByOne(_FixOnce, ast.NodeTransformer):
    """
    Injector changed range(n) → range(n-1) and range(x, n+1) → range(x, n).
    Fix adds 1 back to the stop argument:
        range(n)    → range(n+1)
        range(x, n) → range(x, n+1)   when n is a Name or BinOp
        range(x, k) → range(x, k+1)   when k is a constant integer
    """
    def __init__(self): _FixOnce.__init__(self)
 
    def _add_one(self, arg):
        if isinstance(arg, ast.Constant) and isinstance(arg.value, int):
            return ast.Constant(value=arg.value + 1)
        # n  →  n + 1
        return ast.BinOp(left=arg, op=ast.Add(), right=ast.Constant(value=1))
 
    def visit_Call(self, node):
        if not self.done and isinstance(node.func, ast.Name) and node.func.id == 'range':
            stop_idx = 0 if len(node.args) == 1 else 1
            if stop_idx < len(node.args):
                node.args[stop_idx] = self._add_one(node.args[stop_idx])
                self.done = True
                self.modified_line = getattr(node, 'lineno', None)
        self.generic_visit(node)
        return node
 
 
# ─────────────────────────────────────────────────────────────────────────────
# ACTION 2 — Flip boolean return  (self-inverse)
# ─────────────────────────────────────────────────────────────────────────────
 
class _FixFlipBoolean(_FixOnce, ast.NodeTransformer):
    def __init__(self): _FixOnce.__init__(self)
    def visit_Return(self, node):
        if not self.done and node.value is not None:
            if isinstance(node.value, ast.Constant):
                if node.value.value is True:
                    node.value = ast.Constant(value=False)
                    self.done = True
                    self.modified_line = getattr(node, 'lineno', None)
                elif node.value.value is False:
                    node.value = ast.Constant(value=True)
                    self.done = True
                    self.modified_line = getattr(node, 'lineno', None)
        return node
 
 
# ─────────────────────────────────────────────────────────────────────────────
# ACTION 3 — Swap variable reference  (self-inverse)
# ─────────────────────────────────────────────────────────────────────────────
 
class _FixSwapVariable(_FixOnce, ast.NodeTransformer):
    def __init__(self): _FixOnce.__init__(self)
    def visit_BinOp(self, node):
        if not self.done:
            if isinstance(node.left, ast.Name) and isinstance(node.right, ast.Name):
                if node.left.id != node.right.id:
                    node.left.id, node.right.id = node.right.id, node.left.id
                    self.done = True
                    self.modified_line = getattr(node, 'lineno', None)
        self.generic_visit(node)
        return node
 
 
# ─────────────────────────────────────────────────────────────────────────────
# ACTION 4 — Invert conditional  (smart: unwraps `not` if present, else adds it)
# ─────────────────────────────────────────────────────────────────────────────
 
class _FixInvertConditional(_FixOnce, ast.NodeTransformer):
    """
    If the bug is `if not (cond)`, unwrapping the `not` restores `if cond`.
    If no `not` wrapper exists (different kind of conditional bug), we add one.
    The agent learns from reward which direction was correct.
    """
    def __init__(self): _FixOnce.__init__(self)
    def visit_If(self, node):
        if not self.done:
            if (isinstance(node.test, ast.UnaryOp)
                    and isinstance(node.test.op, ast.Not)):
                # Bug was adding `not` — remove it
                node.test = node.test.operand
            else:
                # Try adding `not`
                node.test = ast.UnaryOp(op=ast.Not(), operand=node.test)
            self.done = True
            self.modified_line = getattr(node, 'lineno', None)
        self.generic_visit(node)
        return node
 
 
# ─────────────────────────────────────────────────────────────────────────────
# ACTION 5 — Wrong initial value  (self-inverse: 0 ↔ 1)
# ─────────────────────────────────────────────────────────────────────────────
 
class _FixWrongInitialValue(_FixOnce, ast.NodeTransformer):
    def __init__(self): _FixOnce.__init__(self)
    def visit_Assign(self, node):
        if not self.done and isinstance(node.value, ast.Constant):
            v = node.value.value
            if v == 0:
                node.value = ast.Constant(value=1)
                self.done = True
                self.modified_line = getattr(node, 'lineno', None)
            elif v == 1:
                node.value = ast.Constant(value=0)
                self.done = True
                self.modified_line = getattr(node, 'lineno', None)
        if not self.done:
            self.generic_visit(node)
        return node
 
 
# ─────────────────────────────────────────────────────────────────────────────
# ACTION 6 — Wrong arithmetic operator  (self-inverse)
# ─────────────────────────────────────────────────────────────────────────────
 
ARITH_SWAPS = {
    ast.Add: ast.Sub,   ast.Sub: ast.Add,
    ast.Mult: ast.FloorDiv, ast.FloorDiv: ast.Mult,
}
 
class _FixWrongArithmetic(_FixOnce, ast.NodeTransformer):
    def __init__(self): _FixOnce.__init__(self)
    def visit_BinOp(self, node):
        if not self.done and type(node.op) in ARITH_SWAPS:
            node.op = ARITH_SWAPS[type(node.op)]()
            self.done = True
            self.modified_line = getattr(node, 'lineno', None)
        self.generic_visit(node)
        return node
    def visit_AugAssign(self, node):
        if not self.done and type(node.op) in ARITH_SWAPS:
            node.op = ARITH_SWAPS[type(node.op)]()
            self.done = True
            self.modified_line = getattr(node, 'lineno', None)
        self.generic_visit(node)
        return node
 
 
# ─────────────────────────────────────────────────────────────────────────────
# ACTION 7 — Wrong return value
# ─────────────────────────────────────────────────────────────────────────────
 
class _FixWrongReturnValue(_FixOnce, ast.NodeTransformer):
    """
    The injector replaced the first non-boolean return with `None`.
    Fix: find `return None` and replace it with the most recently
    assigned local variable in the function body.
 
    Strategy:
      1. Walk the function body, collect variable names from assignments
         in order (excluding loop variables and parameters).
      2. On `return None`, substitute the last collected variable.
 
    If no local variable is found, try the last parameter instead.
    If nothing at all is found, leave as-is (no-op).
    """
    def __init__(self):
        _FixOnce.__init__(self)
        self.self_assigned = []
        self.self_params = []
 
    def visit_FunctionDef(self, node):
        self.self_params = [arg.arg for arg in node.args.args]
        assigned = []
        for stmt in ast.walk(node):
            if isinstance(stmt, ast.Assign):
                for target in stmt.targets:
                    if isinstance(target, ast.Name):
                        name = target.id
                        if name not in self.self_params and name not in assigned:
                            assigned.append(name)
            elif isinstance(stmt, ast.AugAssign):
                if isinstance(stmt.target, ast.Name):
                    name = stmt.target.id
                    if name not in self.self_params and name not in assigned:
                        assigned.append(name)
        self.self_assigned = assigned
        self.generic_visit(node)
        return node
 
    def visit_Return(self, node):
        if not self.done and node.value is not None:
            is_none = isinstance(node.value, ast.Constant) and node.value.value is None
            if is_none:
                # Try local variables first, then params
                candidates = self.self_assigned or self.self_params
                if candidates:
                    node.value = ast.Name(id=candidates[-1], ctx=ast.Load())
                    self.done = True
                    self.modified_line = getattr(node, 'lineno', None)
        return node
 
 
# ─────────────────────────────────────────────────────────────────────────────
# FIX REGISTRY
# ─────────────────────────────────────────────────────────────────────────────
 
_FIXERS = {
    0: _FixSwapComparison,
    1: _FixOffByOne,
    2: _FixFlipBoolean,
    3: _FixSwapVariable,
    4: _FixInvertConditional,
    5: _FixWrongInitialValue,
    6: _FixWrongArithmetic,
    7: _FixWrongReturnValue,
}
 
 
# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────────────────────
 
def apply_fix(source_code: str, action_id: int) -> dict:
    """
    Apply fix action `action_id` to `source_code`.
 
    Returns:
        {
            "modified_code": str,    # transformed code, or original on no-op
            "applied":       bool,   # True if the action found a node to change
            "action_id":     int,    # echoed for logging
            "modified_line": int|None  # source line that was changed
        }
 
    Never raises — returns applied=False on any error.
    """
    if action_id not in _FIXERS:
        return {
            "modified_code": source_code,
            "applied": False,
            "action_id": action_id,
            "modified_line": None,
        }
 
    try:
        original_unparsed = ast.unparse(ast.parse(source_code))
        tree = ast.parse(source_code)
 
        transformer = _FIXERS[action_id]()
        transformer.visit(tree)
 
        if not transformer.done:
            return {
                "modified_code": source_code,
                "applied": False,
                "action_id": action_id,
                "modified_line": None,
            }
 
        ast.fix_missing_locations(tree)
        modified_code = ast.unparse(tree)
 
        # Safety: if unparse produced the same code, treat as no-op
        if modified_code == original_unparsed:
            return {
                "modified_code": source_code,
                "applied": False,
                "action_id": action_id,
                "modified_line": None,
            }
 
        return {
            "modified_code": modified_code,
            "applied": True,
            "action_id": action_id,
            "modified_line": transformer.modified_line,
        }
 
    except Exception:
        return {
            "modified_code": source_code,
            "applied": False,
            "action_id": action_id,
            "modified_line": None,
        }
 
 
def action_name(action_id: int) -> str:
    """Return the human-readable name for an action ID."""
    return ACTION_NAMES.get(action_id, f"unknown_action_{action_id}")
 
 
def available_actions() -> list:
    """Return list of all valid action IDs."""
    return list(_FIXERS.keys())