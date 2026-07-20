"""
BugForge — Action Masker
=========================
Fast AST-based check: which of the 8 fix actions are applicable
to the current code, WITHOUT actually modifying it.

Why this matters:
    If code has no comparison operators, action 0 (swap_comparison)
    is always a no-op. Letting the agent pick it wastes an attempt
    AND confuses training. Masking forces the agent to only choose
    from actions that can actually do something.

Expected impact: +15–20% solve rate.
"""

import ast
from typing import List


# ── Fast applicability checks (read-only AST walk) ───────────────────────────

def _has_comparison(tree) -> bool:
    return any(isinstance(n, ast.Compare) for n in ast.walk(tree))


def _has_range_call(tree) -> bool:
    return any(
        isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == 'range'
        for n in ast.walk(tree)
    )


def _has_bool_return(tree) -> bool:
    return any(
        isinstance(n, ast.Return)
        and n.value is not None
        and isinstance(n.value, ast.Constant)
        and isinstance(n.value.value, bool)
        for n in ast.walk(tree)
    )


def _has_two_name_binop(tree) -> bool:
    return any(
        isinstance(n, ast.BinOp)
        and isinstance(n.left, ast.Name)
        and isinstance(n.right, ast.Name)
        and n.left.id != n.right.id
        for n in ast.walk(tree)
    )


def _has_if_statement(tree) -> bool:
    return any(isinstance(n, ast.If) for n in ast.walk(tree))


def _has_zero_or_one_assign(tree) -> bool:
    return any(
        isinstance(n, ast.Assign)
        and isinstance(n.value, ast.Constant)
        and n.value.value in (0, 1)
        for n in ast.walk(tree)
    )


def _has_arithmetic_op(tree) -> bool:
    ARITH = (ast.Add, ast.Sub, ast.Mult, ast.FloorDiv)
    return any(
        (isinstance(n, ast.BinOp) and isinstance(n.op, ARITH))
        or (isinstance(n, ast.AugAssign) and isinstance(n.op, ARITH))
        for n in ast.walk(tree)
    )


def _has_none_return(tree) -> bool:
    return any(
        isinstance(n, ast.Return)
        and n.value is not None
        and isinstance(n.value, ast.Constant)
        and n.value.value is None
        for n in ast.walk(tree)
    )


# Mapping: action_id → checker function
_CHECKERS = {
    0: _has_comparison,
    1: _has_range_call,
    2: _has_bool_return,
    3: _has_two_name_binop,
    4: _has_if_statement,
    5: _has_zero_or_one_assign,
    6: _has_arithmetic_op,
    7: _has_none_return,
}


def get_action_mask(code: str) -> List[int]:
    """
    Returns list of action IDs that are applicable to `code`.
    Falls back to all 8 actions if code has a syntax error.

    Usage:
        valid = get_action_mask(current_code)
        action = agent.choose_action(state_vector, epsilon, valid_actions=valid)
    """
    try:
        tree = ast.parse(code)
        valid = [
            action_id
            for action_id, check in _CHECKERS.items()
            if check(tree)
        ]
        # Always return at least all actions as fallback
        return valid if valid else list(range(8))
    except SyntaxError:
        # Syntax error code — any action might help
        return list(range(8))


def mask_to_binary(valid_actions: List[int], n_actions: int = 8):
    """
    Convert list of valid action IDs to binary mask tensor.
    Used internally by agent for masked Q-value selection.

    Example: [0, 4, 6] → [1, 0, 0, 0, 1, 0, 1, 0]
    """
    import torch
    mask = torch.zeros(n_actions)
    for a in valid_actions:
        mask[a] = 1.0
    return mask