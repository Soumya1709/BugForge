#!/usr/bin/env python3
"""
BugForge Dataset Generator
==========================
Generates verified buggy/correct Python code pairs with test cases.

Each example is verified:
  - Correct code  → ALL tests pass
  - Buggy code    → AT LEAST ONE test fails

Output: dataset/examples/*.json  +  dataset/dataset_index.json

Usage:
    python generate_dataset.py
    python generate_dataset.py --target 300   # default
    python generate_dataset.py --target 150   # smaller run
"""

import ast
import json
import os
import subprocess
import sys
import tempfile
import random
import argparse
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
EXAMPLES_DIR = SCRIPT_DIR / "examples"
EXAMPLES_DIR.mkdir(exist_ok=True)

TIMEOUT = 5  # seconds per test run

# ─────────────────────────────────────────────────────────────────────────────
# BUG TYPE REGISTRY
# ─────────────────────────────────────────────────────────────────────────────

BUG_NAMES = {
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
# AST INJECTORS  (one bug, first matching node, deterministic)
# ─────────────────────────────────────────────────────────────────────────────

COMP_SWAPS = {
    ast.Lt: ast.Gt,   ast.Gt: ast.Lt,
    ast.LtE: ast.GtE, ast.GtE: ast.LtE,
    ast.Eq: ast.NotEq, ast.NotEq: ast.Eq,
}

ARITH_SWAPS = {
    ast.Add: ast.Sub,   ast.Sub: ast.Add,
    ast.Mult: ast.FloorDiv, ast.FloorDiv: ast.Mult,
}


class _Once:
    """
    Base for all injectors.
    skip_lines: set of source line numbers already modified — injector will
                skip any AST node whose lineno is in this set, guaranteeing
                at most one bug per line across multiple injections.
    After a successful mutation, self.done = True and self.modified_line
    holds the line number that was changed.
    """
    def __init__(self, skip_lines=None):
        self.done = False
        self.skip_lines = skip_lines or set()
        self.modified_line = None

    def _clear(self, lineno):
        """Return True if this line is safe to modify."""
        return lineno not in self.skip_lines


class SwapComparisonOp(_Once, ast.NodeTransformer):
    def __init__(self, skip_lines=None): _Once.__init__(self, skip_lines)
    def visit_Compare(self, node):
        ln = getattr(node, 'lineno', None)
        if not self.done and ln is not None and self._clear(ln):
            for i, op in enumerate(node.ops):
                if type(op) in COMP_SWAPS:
                    node.ops[i] = COMP_SWAPS[type(op)]()
                    self.done = True
                    self.modified_line = ln
                    break
        self.generic_visit(node)
        return node


class OffByOne(_Once, ast.NodeTransformer):
    """Modifies stop argument of range() — handles range(n) and range(x, n+1)."""
    def __init__(self, skip_lines=None): _Once.__init__(self, skip_lines)

    def _shift(self, arg):
        if isinstance(arg, ast.Constant) and isinstance(arg.value, int) and arg.value > 0:
            return ast.Constant(value=arg.value - 1)
        if (isinstance(arg, ast.BinOp) and isinstance(arg.op, ast.Add)
                and isinstance(arg.right, ast.Constant) and arg.right.value == 1):
            return arg.left
        if (isinstance(arg, ast.BinOp) and isinstance(arg.op, ast.Sub)
                and isinstance(arg.right, ast.Constant) and arg.right.value == 1):
            return ast.BinOp(left=arg.left, op=ast.Add(), right=ast.Constant(value=1))
        return None

    def visit_Call(self, node):
        ln = getattr(node, 'lineno', None)
        if not self.done and ln is not None and self._clear(ln):
            if isinstance(node.func, ast.Name) and node.func.id == 'range':
                stop_idx = 0 if len(node.args) == 1 else 1
                if stop_idx < len(node.args):
                    shifted = self._shift(node.args[stop_idx])
                    if shifted is not None:
                        node.args[stop_idx] = shifted
                        self.done = True
                        self.modified_line = ln
        self.generic_visit(node)
        return node


class FlipBooleanReturn(_Once, ast.NodeTransformer):
    def __init__(self, skip_lines=None): _Once.__init__(self, skip_lines)
    def visit_Return(self, node):
        ln = getattr(node, 'lineno', None)
        if not self.done and ln is not None and self._clear(ln) and node.value is not None:
            if isinstance(node.value, ast.Constant):
                if node.value.value is True:
                    node.value = ast.Constant(value=False)
                    self.done = True; self.modified_line = ln
                elif node.value.value is False:
                    node.value = ast.Constant(value=True)
                    self.done = True; self.modified_line = ln
        return node


class SwapVariableRef(_Once, ast.NodeTransformer):
    """Swaps left/right Name nodes inside the first qualifying BinOp."""
    def __init__(self, skip_lines=None): _Once.__init__(self, skip_lines)
    def visit_BinOp(self, node):
        ln = getattr(node, 'lineno', None)
        if not self.done and ln is not None and self._clear(ln):
            if isinstance(node.left, ast.Name) and isinstance(node.right, ast.Name):
                if node.left.id != node.right.id:
                    node.left.id, node.right.id = node.right.id, node.left.id
                    self.done = True; self.modified_line = ln
        self.generic_visit(node)
        return node


class InvertConditional(_Once, ast.NodeTransformer):
    def __init__(self, skip_lines=None): _Once.__init__(self, skip_lines)
    def visit_If(self, node):
        ln = getattr(node, 'lineno', None)
        if not self.done and ln is not None and self._clear(ln):
            node.test = ast.UnaryOp(op=ast.Not(), operand=node.test)
            self.done = True; self.modified_line = ln
        self.generic_visit(node)
        return node


class WrongInitialValue(_Once, ast.NodeTransformer):
    """Flips 0 ↔ 1 in the first assignment with a numeric literal."""
    def __init__(self, skip_lines=None): _Once.__init__(self, skip_lines)
    def visit_Assign(self, node):
        ln = getattr(node, 'lineno', None)
        if not self.done and ln is not None and self._clear(ln):
            if isinstance(node.value, ast.Constant):
                v = node.value.value
                if v == 0:
                    node.value = ast.Constant(value=1)
                    self.done = True; self.modified_line = ln
                elif v == 1:
                    node.value = ast.Constant(value=0)
                    self.done = True; self.modified_line = ln
        if not self.done:
            self.generic_visit(node)
        return node


class WrongArithmeticOp(_Once, ast.NodeTransformer):
    def __init__(self, skip_lines=None): _Once.__init__(self, skip_lines)
    def visit_BinOp(self, node):
        ln = getattr(node, 'lineno', None)
        if not self.done and ln is not None and self._clear(ln) and type(node.op) in ARITH_SWAPS:
            node.op = ARITH_SWAPS[type(node.op)]()
            self.done = True; self.modified_line = ln
        self.generic_visit(node)
        return node
    def visit_AugAssign(self, node):
        ln = getattr(node, 'lineno', None)
        if not self.done and ln is not None and self._clear(ln) and type(node.op) in ARITH_SWAPS:
            node.op = ARITH_SWAPS[type(node.op)]()
            self.done = True; self.modified_line = ln
        self.generic_visit(node)
        return node


class WrongReturnValue(_Once, ast.NodeTransformer):
    """Replaces the first non-boolean return value with None."""
    def __init__(self, skip_lines=None): _Once.__init__(self, skip_lines)
    def visit_Return(self, node):
        ln = getattr(node, 'lineno', None)
        if not self.done and ln is not None and self._clear(ln) and node.value is not None:
            is_bool = isinstance(node.value, ast.Constant) and isinstance(node.value.value, bool)
            if not is_bool:
                node.value = ast.Constant(value=None)
                self.done = True; self.modified_line = ln
        return node


INJECTORS = {
    0: SwapComparisonOp,
    1: OffByOne,
    2: FlipBooleanReturn,
    3: SwapVariableRef,
    4: InvertConditional,
    5: WrongInitialValue,
    6: WrongArithmeticOp,
    7: WrongReturnValue,
}


def inject_bug(source: str, bug_type: int, skip_lines=None):
    """
    Single-bug injection (backward-compatible).
    Returns (buggy_source, True) or (None, False) if the bug type doesn't apply.
    """
    try:
        tree = ast.parse(source)
        transformer = INJECTORS[bug_type](skip_lines=skip_lines)
        transformer.visit(tree)
        if not transformer.done:
            return None, False
        ast.fix_missing_locations(tree)
        result = ast.unparse(tree)
        if result == ast.unparse(ast.parse(source)):
            return None, False
        return result, True
    except Exception:
        return None, False


def inject_multi_bug(source: str, bug_types: list):
    """
    Inject multiple bugs into one function — one bug per source line.

    Strategy: parse the source ONCE, then run each injector sequentially
    on the same live AST tree. Each injector receives the set of lines
    already modified so it skips those lines. Because we never re-parse
    between injections, the original lineno attributes on unmodified nodes
    stay stable throughout, making skip_lines tracking reliable.

    Returns:
        (buggy_code, applied_bug_types, modified_lines)
        buggy_code        – unparsed source with all bugs injected
        applied_bug_types – subset of bug_types that actually applied
        modified_lines    – source line numbers that were changed (same order)

    Returns (None, [], []) if zero bug types could be applied.
    """
    try:
        original_unparsed = ast.unparse(ast.parse(source))
        tree = ast.parse(source)
        used_lines = set()
        applied_bugs = []
        modified_lines = []

        for bug_type in bug_types:
            transformer = INJECTORS[bug_type](skip_lines=used_lines)
            transformer.visit(tree)
            if transformer.done:
                applied_bugs.append(bug_type)
                if transformer.modified_line is not None:
                    used_lines.add(transformer.modified_line)
                    modified_lines.append(transformer.modified_line)

        if not applied_bugs:
            return None, [], []

        ast.fix_missing_locations(tree)
        buggy_code = ast.unparse(tree)

        if buggy_code == original_unparsed:
            return None, [], []

        return buggy_code, applied_bugs, modified_lines
    except Exception:
        return None, [], []


# ─────────────────────────────────────────────────────────────────────────────
# TEST RUNNER  (subprocess-isolated, timeout-safe)
# ─────────────────────────────────────────────────────────────────────────────

def _build_runner_script(code: str, tests: list) -> str:
    blocks = ""
    for t in tests:
        blocks += f"""
try:
    {t}
    _p += 1
except Exception:
    _f += 1
"""
    return f"""{code}

_p = 0
_f = 0
{blocks}
print(f"{{_p}},{{_f}}")
"""


def run_tests(code: str, tests: list, timeout: int = TIMEOUT) -> dict:
    script = _build_runner_script(code, tests)
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(script)
        fname = f.name
    try:
        proc = subprocess.run(
            [sys.executable, fname],
            capture_output=True, text=True, timeout=timeout
        )
        out = proc.stdout.strip()
        if ',' in out:
            p, fail = map(int, out.split(','))
            total = p + fail
            return {
                "passed": p, "failed": fail, "total": total,
                "pass_rate": p / total if total > 0 else 0.0,
                "timed_out": False, "error_line": None,
            }
        return {"passed": 0, "failed": 0, "total": 0,
                "pass_rate": 0.0, "timed_out": False, "error_line": None}
    except subprocess.TimeoutExpired:
        return {"passed": 0, "failed": 0, "total": 0,
                "pass_rate": 0.0, "timed_out": True, "error_line": None}
    except Exception:
        return {"passed": 0, "failed": 0, "total": 0,
                "pass_rate": 0.0, "timed_out": False, "error_line": None}
    finally:
        os.unlink(fname)


def get_error_line(code: str):
    try:
        ast.parse(code)
        return None
    except SyntaxError as e:
        return e.lineno


# ─────────────────────────────────────────────────────────────────────────────
# BASE FUNCTIONS  (50 correct implementations + test cases)
# ─────────────────────────────────────────────────────────────────────────────

BASE_FUNCTIONS = [

    # ── SORTING ──────────────────────────────────────────────────────────────
    {
        "name": "bubble_sort",
        "correct_code": """\
def bubble_sort(arr):
    n = len(arr)
    for i in range(n):
        for j in range(0, n - i - 1):
            if arr[j] > arr[j + 1]:
                arr[j], arr[j + 1] = arr[j + 1], arr[j]
    return arr""",
        "tests": [
            "assert bubble_sort([64, 34, 25, 12, 22]) == [12, 22, 25, 34, 64]",
            "assert bubble_sort([3, 1, 2]) == [1, 2, 3]",
            "assert bubble_sort([1, 2, 3]) == [1, 2, 3]",
        ],
    },
    {
        "name": "selection_sort",
        "correct_code": """\
def selection_sort(arr):
    n = len(arr)
    for i in range(n):
        min_idx = i
        for j in range(i + 1, n):
            if arr[j] < arr[min_idx]:
                min_idx = j
        arr[i], arr[min_idx] = arr[min_idx], arr[i]
    return arr""",
        "tests": [
            "assert selection_sort([64, 25, 12, 22, 11]) == [11, 12, 22, 25, 64]",
            "assert selection_sort([3, 1, 2]) == [1, 2, 3]",
            "assert selection_sort([5]) == [5]",
        ],
    },
    {
        "name": "insertion_sort",
        "correct_code": """\
def insertion_sort(arr):
    for i in range(1, len(arr)):
        key = arr[i]
        j = i - 1
        while j >= 0 and arr[j] > key:
            arr[j + 1] = arr[j]
            j -= 1
        arr[j + 1] = key
    return arr""",
        "tests": [
            "assert insertion_sort([12, 11, 13, 5, 6]) == [5, 6, 11, 12, 13]",
            "assert insertion_sort([3, 1, 2]) == [1, 2, 3]",
            "assert insertion_sort([1]) == [1]",
        ],
    },
    {
        "name": "sort_array",          # naming variant of bubble sort
        "correct_code": """\
def sort_array(data):
    sz = len(data)
    for x in range(sz):
        for y in range(0, sz - x - 1):
            if data[y] > data[y + 1]:
                data[y], data[y + 1] = data[y + 1], data[y]
    return data""",
        "tests": [
            "assert sort_array([5, 2, 8, 1, 9]) == [1, 2, 5, 8, 9]",
            "assert sort_array([3, 1]) == [1, 3]",
            "assert sort_array([4, 4, 4]) == [4, 4, 4]",
        ],
    },

    # ── SEARCHING ─────────────────────────────────────────────────────────────
    {
        "name": "linear_search",
        "correct_code": """\
def linear_search(arr, target):
    for i in range(len(arr)):
        if arr[i] == target:
            return i
    return -1""",
        "tests": [
            "assert linear_search([3, 1, 4, 1, 5], 4) == 2",
            "assert linear_search([1, 2, 3], 9) == -1",
            "assert linear_search([7], 7) == 0",
        ],
    },
    {
        "name": "binary_search",
        "correct_code": """\
def binary_search(arr, target):
    left = 0
    right = len(arr) - 1
    while left <= right:
        mid = (left + right) // 2
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            left = mid + 1
        else:
            right = mid - 1
    return -1""",
        "tests": [
            "assert binary_search([1, 3, 5, 7, 9], 5) == 2",
            "assert binary_search([1, 3, 5, 7, 9], 1) == 0",
            "assert binary_search([1, 3, 5, 7, 9], 10) == -1",
        ],
    },
    {
        "name": "find_element",        # terse-named linear search
        "correct_code": """\
def find_element(lst, val):
    for idx in range(len(lst)):
        if lst[idx] == val:
            return idx
    return -1""",
        "tests": [
            "assert find_element([10, 20, 30, 40], 30) == 2",
            "assert find_element([1, 2, 3], 5) == -1",
            "assert find_element([99], 99) == 0",
        ],
    },

    # ── MATH ──────────────────────────────────────────────────────────────────
    {
        "name": "factorial",
        "correct_code": """\
def factorial(n):
    result = 1
    for i in range(1, n + 1):
        result *= i
    return result""",
        "tests": [
            "assert factorial(5) == 120",
            "assert factorial(0) == 1",
            "assert factorial(3) == 6",
        ],
    },
    {
        "name": "compute_factorial",   # verbose-named variant
        "correct_code": """\
def compute_factorial(input_number):
    accumulator = 1
    for multiplier in range(1, input_number + 1):
        accumulator *= multiplier
    return accumulator""",
        "tests": [
            "assert compute_factorial(4) == 24",
            "assert compute_factorial(1) == 1",
            "assert compute_factorial(6) == 720",
        ],
    },
    {
        "name": "fibonacci",
        "correct_code": """\
def fibonacci(n):
    if n <= 0:
        return 0
    if n == 1:
        return 1
    a = 0
    b = 1
    for i in range(2, n + 1):
        a, b = b, a + b
    return b""",
        "tests": [
            "assert fibonacci(0) == 0",
            "assert fibonacci(1) == 1",
            "assert fibonacci(7) == 13",
        ],
    },
    {
        "name": "nth_fibonacci",
        "correct_code": """\
def nth_fibonacci(n):
    if n == 0:
        return 0
    if n == 1:
        return 1
    prev = 0
    curr = 1
    for i in range(2, n + 1):
        prev, curr = curr, prev + curr
    return curr""",
        "tests": [
            "assert nth_fibonacci(6) == 8",
            "assert nth_fibonacci(0) == 0",
            "assert nth_fibonacci(10) == 55",
        ],
    },
    {
        "name": "power",
        "correct_code": """\
def power(base, exp):
    result = 1
    for i in range(exp):
        result *= base
    return result""",
        "tests": [
            "assert power(2, 10) == 1024",
            "assert power(3, 3) == 27",
            "assert power(5, 0) == 1",
        ],
    },
    {
        "name": "gcd",
        "correct_code": """\
def gcd(a, b):
    while b != 0:
        a, b = b, a % b
    return a""",
        "tests": [
            "assert gcd(48, 18) == 6",
            "assert gcd(100, 75) == 25",
            "assert gcd(7, 5) == 1",
        ],
    },
    {
        "name": "lcm",
        "correct_code": """\
def lcm(a, b):
    g = a
    temp = b
    while temp != 0:
        g, temp = temp, g % temp
    return (a * b) // g""",
        "tests": [
            "assert lcm(4, 6) == 12",
            "assert lcm(3, 5) == 15",
            "assert lcm(7, 7) == 7",
        ],
    },
    {
        "name": "is_prime",
        "correct_code": """\
def is_prime(n):
    if n < 2:
        return False
    for i in range(2, int(n ** 0.5) + 1):
        if n % i == 0:
            return False
    return True""",
        "tests": [
            "assert is_prime(7) == True",
            "assert is_prime(4) == False",
            "assert is_prime(1) == False",
        ],
    },
    {
        "name": "check_prime",         # terse-named variant
        "correct_code": """\
def check_prime(num):
    if num < 2:
        return False
    for d in range(2, num):
        if num % d == 0:
            return False
    return True""",
        "tests": [
            "assert check_prime(11) == True",
            "assert check_prime(9) == False",
            "assert check_prime(2) == True",
        ],
    },
    {
        "name": "sum_digits",
        "correct_code": """\
def sum_digits(n):
    total = 0
    n = abs(n)
    while n > 0:
        total += n % 10
        n //= 10
    return total""",
        "tests": [
            "assert sum_digits(123) == 6",
            "assert sum_digits(9) == 9",
            "assert sum_digits(100) == 1",
        ],
    },
    {
        "name": "count_digits",
        "correct_code": """\
def count_digits(n):
    if n == 0:
        return 1
    count = 0
    n = abs(n)
    while n > 0:
        count += 1
        n //= 10
    return count""",
        "tests": [
            "assert count_digits(12345) == 5",
            "assert count_digits(0) == 1",
            "assert count_digits(100) == 3",
        ],
    },
    {
        "name": "celsius_to_fahrenheit",
        "correct_code": """\
def celsius_to_fahrenheit(c):
    return c * 9 / 5 + 32""",
        "tests": [
            "assert celsius_to_fahrenheit(0) == 32.0",
            "assert celsius_to_fahrenheit(100) == 212.0",
            "assert celsius_to_fahrenheit(-40) == -40.0",
        ],
    },
    {
        "name": "is_perfect_number",
        "correct_code": """\
def is_perfect_number(n):
    if n < 2:
        return False
    total = 0
    for i in range(1, n):
        if n % i == 0:
            total += i
    return total == n""",
        "tests": [
            "assert is_perfect_number(6) == True",
            "assert is_perfect_number(28) == True",
            "assert is_perfect_number(12) == False",
        ],
    },
    {
        "name": "absolute_value",
        "correct_code": """\
def absolute_value(n):
    if n < 0:
        return -n
    return n""",
        "tests": [
            "assert absolute_value(-5) == 5",
            "assert absolute_value(3) == 3",
            "assert absolute_value(0) == 0",
        ],
    },
    {
        "name": "binary_to_decimal",
        "correct_code": """\
def binary_to_decimal(binary_str):
    result = 0
    power = 0
    for bit in reversed(binary_str):
        if bit == '1':
            result += 2 ** power
        power += 1
    return result""",
        "tests": [
            "assert binary_to_decimal('1010') == 10",
            "assert binary_to_decimal('1111') == 15",
            "assert binary_to_decimal('0') == 0",
        ],
    },
    {
        "name": "max_of_three",
        "correct_code": """\
def max_of_three(a, b, c):
    if a >= b and a >= c:
        return a
    if b >= c:
        return b
    return c""",
        "tests": [
            "assert max_of_three(3, 1, 2) == 3",
            "assert max_of_three(1, 5, 3) == 5",
            "assert max_of_three(2, 4, 4) == 4",
        ],
    },

    # ── STRINGS ───────────────────────────────────────────────────────────────
    {
        "name": "is_palindrome",
        "correct_code": """\
def is_palindrome(s):
    left = 0
    right = len(s) - 1
    while left < right:
        if s[left] != s[right]:
            return False
        left += 1
        right -= 1
    return True""",
        "tests": [
            "assert is_palindrome('racecar') == True",
            "assert is_palindrome('hello') == False",
            "assert is_palindrome('a') == True",
        ],
    },
    {
        "name": "count_vowels",
        "correct_code": """\
def count_vowels(s):
    count = 0
    for ch in s:
        if ch in 'aeiouAEIOU':
            count += 1
    return count""",
        "tests": [
            "assert count_vowels('hello world') == 3",
            "assert count_vowels('rhythm') == 0",
            "assert count_vowels('aeiou') == 5",
        ],
    },
    {
        "name": "reverse_string",
        "correct_code": """\
def reverse_string(s):
    result = ''
    for i in range(len(s) - 1, -1, -1):
        result += s[i]
    return result""",
        "tests": [
            "assert reverse_string('hello') == 'olleh'",
            "assert reverse_string('a') == 'a'",
            "assert reverse_string('abcd') == 'dcba'",
        ],
    },
    {
        "name": "flip_string",         # naming variant
        "correct_code": """\
def flip_string(text):
    out = ''
    idx = len(text) - 1
    while idx >= 0:
        out += text[idx]
        idx -= 1
    return out""",
        "tests": [
            "assert flip_string('world') == 'dlrow'",
            "assert flip_string('x') == 'x'",
            "assert flip_string('ab') == 'ba'",
        ],
    },
    {
        "name": "count_occurrences",
        "correct_code": """\
def count_occurrences(s, char):
    count = 0
    for ch in s:
        if ch == char:
            count += 1
    return count""",
        "tests": [
            "assert count_occurrences('hello', 'l') == 2",
            "assert count_occurrences('banana', 'a') == 3",
            "assert count_occurrences('xyz', 'a') == 0",
        ],
    },
    {
        "name": "is_anagram",
        "correct_code": """\
def is_anagram(s1, s2):
    if len(s1) != len(s2):
        return False
    return sorted(s1) == sorted(s2)""",
        "tests": [
            "assert is_anagram('listen', 'silent') == True",
            "assert is_anagram('hello', 'world') == False",
            "assert is_anagram('abc', 'cab') == True",
        ],
    },
    {
        "name": "string_length",
        "correct_code": """\
def string_length(s):
    count = 0
    for ch in s:
        count += 1
    return count""",
        "tests": [
            "assert string_length('hello') == 5",
            "assert string_length('') == 0",
            "assert string_length('ab') == 2",
        ],
    },
    {
        "name": "capitalize_first",
        "correct_code": """\
def capitalize_first(s):
    if len(s) == 0:
        return s
    return s[0].upper() + s[1:]""",
        "tests": [
            "assert capitalize_first('hello') == 'Hello'",
            "assert capitalize_first('') == ''",
            "assert capitalize_first('world') == 'World'",
        ],
    },
    {
        "name": "count_words",
        "correct_code": """\
def count_words(s):
    if s == '':
        return 0
    return len(s.split())""",
        "tests": [
            "assert count_words('hello world') == 2",
            "assert count_words('') == 0",
            "assert count_words('one two three four') == 4",
        ],
    },
    {
        "name": "starts_with",
        "correct_code": """\
def starts_with(s, prefix):
    if len(prefix) > len(s):
        return False
    for i in range(len(prefix)):
        if s[i] != prefix[i]:
            return False
    return True""",
        "tests": [
            "assert starts_with('hello', 'he') == True",
            "assert starts_with('world', 'he') == False",
            "assert starts_with('abc', 'abc') == True",
        ],
    },

    # ── LISTS ─────────────────────────────────────────────────────────────────
    {
        "name": "find_max",
        "correct_code": """\
def find_max(lst):
    max_val = lst[0]
    for num in lst:
        if num > max_val:
            max_val = num
    return max_val""",
        "tests": [
            "assert find_max([3, 1, 4, 1, 5, 9]) == 9",
            "assert find_max([1]) == 1",
            "assert find_max([-3, -1, -2]) == -1",
        ],
    },
    {
        "name": "find_min",
        "correct_code": """\
def find_min(lst):
    min_val = lst[0]
    for num in lst:
        if num < min_val:
            min_val = num
    return min_val""",
        "tests": [
            "assert find_min([3, 1, 4, 1, 5]) == 1",
            "assert find_min([7]) == 7",
            "assert find_min([-1, -3, -2]) == -3",
        ],
    },
    {
        "name": "sum_list",
        "correct_code": """\
def sum_list(lst):
    total = 0
    for num in lst:
        total += num
    return total""",
        "tests": [
            "assert sum_list([1, 2, 3, 4, 5]) == 15",
            "assert sum_list([0]) == 0",
            "assert sum_list([-1, 1]) == 0",
        ],
    },
    {
        "name": "product_list",
        "correct_code": """\
def product_list(lst):
    result = 1
    for num in lst:
        result *= num
    return result""",
        "tests": [
            "assert product_list([1, 2, 3, 4]) == 24",
            "assert product_list([5]) == 5",
            "assert product_list([2, 3, 4]) == 24",
        ],
    },
    {
        "name": "list_average",
        "correct_code": """\
def list_average(lst):
    total = 0
    for num in lst:
        total += num
    return total / len(lst)""",
        "tests": [
            "assert list_average([1, 2, 3, 4, 5]) == 3.0",
            "assert list_average([10, 20]) == 15.0",
            "assert list_average([7]) == 7.0",
        ],
    },
    {
        "name": "is_sorted",
        "correct_code": """\
def is_sorted(lst):
    for i in range(len(lst) - 1):
        if lst[i] > lst[i + 1]:
            return False
    return True""",
        "tests": [
            "assert is_sorted([1, 2, 3, 4]) == True",
            "assert is_sorted([1, 3, 2]) == False",
            "assert is_sorted([1]) == True",
        ],
    },
    {
        "name": "remove_duplicates",
        "correct_code": """\
def remove_duplicates(lst):
    seen = []
    for item in lst:
        if item not in seen:
            seen.append(item)
    return seen""",
        "tests": [
            "assert remove_duplicates([1, 2, 2, 3, 3]) == [1, 2, 3]",
            "assert remove_duplicates([1]) == [1]",
            "assert remove_duplicates([1, 1, 1]) == [1]",
        ],
    },
    {
        "name": "count_greater_than",
        "correct_code": """\
def count_greater_than(lst, threshold):
    count = 0
    for num in lst:
        if num > threshold:
            count += 1
    return count""",
        "tests": [
            "assert count_greater_than([1, 5, 3, 8, 2], 4) == 2",
            "assert count_greater_than([1, 2, 3], 5) == 0",
            "assert count_greater_than([10, 20, 30], 0) == 3",
        ],
    },
    {
        "name": "has_duplicate",
        "correct_code": """\
def has_duplicate(lst):
    seen = []
    for item in lst:
        if item in seen:
            return True
        seen.append(item)
    return False""",
        "tests": [
            "assert has_duplicate([1, 2, 3, 2]) == True",
            "assert has_duplicate([1, 2, 3]) == False",
            "assert has_duplicate([1, 1]) == True",
        ],
    },
    {
        "name": "cumulative_sum",
        "correct_code": """\
def cumulative_sum(lst):
    result = []
    total = 0
    for num in lst:
        total += num
        result.append(total)
    return result""",
        "tests": [
            "assert cumulative_sum([1, 2, 3]) == [1, 3, 6]",
            "assert cumulative_sum([5]) == [5]",
            "assert cumulative_sum([1, -1, 2]) == [1, 0, 2]",
        ],
    },
    {
        "name": "flatten_list",
        "correct_code": """\
def flatten_list(nested):
    result = []
    for sublist in nested:
        for item in sublist:
            result.append(item)
    return result""",
        "tests": [
            "assert flatten_list([[1, 2], [3, 4], [5]]) == [1, 2, 3, 4, 5]",
            "assert flatten_list([[1]]) == [1]",
            "assert flatten_list([[], [1, 2]]) == [1, 2]",
        ],
    },
    {
        "name": "count_even_numbers",
        "correct_code": """\
def count_even_numbers(lst):
    count = 0
    for num in lst:
        if num % 2 == 0:
            count += 1
    return count""",
        "tests": [
            "assert count_even_numbers([1, 2, 3, 4, 6]) == 3",
            "assert count_even_numbers([1, 3, 5]) == 0",
            "assert count_even_numbers([2, 4, 6]) == 3",
        ],
    },
    {
        "name": "rotate_list",
        "correct_code": """\
def rotate_list(lst, k):
    n = len(lst)
    k = k % n
    return lst[k:] + lst[:k]""",
        "tests": [
            "assert rotate_list([1, 2, 3, 4, 5], 2) == [3, 4, 5, 1, 2]",
            "assert rotate_list([1, 2, 3], 0) == [1, 2, 3]",
            "assert rotate_list([1, 2, 3], 3) == [1, 2, 3]",
        ],
    },
    {
        "name": "second_largest",
        "correct_code": """\
def second_largest(lst):
    first = lst[0]
    second = None
    for num in lst[1:]:
        if num > first:
            second = first
            first = num
        elif second is None or num > second:
            if num != first:
                second = num
    return second""",
        "tests": [
            "assert second_largest([3, 1, 4, 1, 5, 9, 2, 6]) == 6",
            "assert second_largest([10, 20, 30]) == 20",
            "assert second_largest([5, 5, 3]) == 3",
        ],
    },

    # ── CONDITIONALS / MISC ───────────────────────────────────────────────────
    {
        "name": "is_even",
        "correct_code": """\
def is_even(n):
    if n % 2 == 0:
        return True
    return False""",
        "tests": [
            "assert is_even(4) == True",
            "assert is_even(7) == False",
            "assert is_even(0) == True",
        ],
    },
    {
        "name": "clamp",
        "correct_code": """\
def clamp(value, low, high):
    if value < low:
        return low
    if value > high:
        return high
    return value""",
        "tests": [
            "assert clamp(5, 1, 10) == 5",
            "assert clamp(-1, 0, 10) == 0",
            "assert clamp(15, 0, 10) == 10",
        ],
    },
    {
        "name": "safe_divide",
        "correct_code": """\
def safe_divide(a, b):
    if b == 0:
        return None
    return a / b""",
        "tests": [
            "assert safe_divide(10, 2) == 5.0",
            "assert safe_divide(7, 0) is None",
            "assert safe_divide(9, 3) == 3.0",
        ],
    },
    {
        "name": "grade_letter",
        "correct_code": """\
def grade_letter(score):
    if score >= 90:
        return 'A'
    if score >= 80:
        return 'B'
    if score >= 70:
        return 'C'
    return 'F'""",
        "tests": [
            "assert grade_letter(95) == 'A'",
            "assert grade_letter(85) == 'B'",
            "assert grade_letter(60) == 'F'",
        ],
    },
    {
        "name": "fizzbuzz_single",
        "correct_code": """\
def fizzbuzz_single(n):
    if n % 15 == 0:
        return 'FizzBuzz'
    if n % 3 == 0:
        return 'Fizz'
    if n % 5 == 0:
        return 'Buzz'
    return str(n)""",
        "tests": [
            "assert fizzbuzz_single(15) == 'FizzBuzz'",
            "assert fizzbuzz_single(3) == 'Fizz'",
            "assert fizzbuzz_single(7) == '7'",
        ],
    },
    {
        "name": "sign_of",
        "correct_code": """\
def sign_of(n):
    if n > 0:
        return 1
    if n < 0:
        return -1
    return 0""",
        "tests": [
            "assert sign_of(5) == 1",
            "assert sign_of(-3) == -1",
            "assert sign_of(0) == 0",
        ],
    },

    # ── EXTRA: BOOLEAN-RETURNING (targets flip_boolean) ──────────────────────
    {
        "name": "is_divisible",
        "correct_code": """\
def is_divisible(n, d):
    if n % d == 0:
        return True
    return False""",
        "tests": [
            "assert is_divisible(10, 5) == True",
            "assert is_divisible(7, 3) == False",
            "assert is_divisible(0, 4) == True",
        ],
    },
    {
        "name": "is_positive",
        "correct_code": """\
def is_positive(n):
    if n > 0:
        return True
    return False""",
        "tests": [
            "assert is_positive(5) == True",
            "assert is_positive(-1) == False",
            "assert is_positive(0) == False",
        ],
    },
    {
        "name": "is_negative",
        "correct_code": """\
def is_negative(n):
    if n < 0:
        return True
    return False""",
        "tests": [
            "assert is_negative(-3) == True",
            "assert is_negative(0) == False",
            "assert is_negative(7) == False",
        ],
    },
    {
        "name": "contains_zero",
        "correct_code": """\
def contains_zero(lst):
    for num in lst:
        if num == 0:
            return True
    return False""",
        "tests": [
            "assert contains_zero([1, 0, 3]) == True",
            "assert contains_zero([1, 2, 3]) == False",
            "assert contains_zero([0]) == True",
        ],
    },
    {
        "name": "all_positive",
        "correct_code": """\
def all_positive(lst):
    for num in lst:
        if num <= 0:
            return False
    return True""",
        "tests": [
            "assert all_positive([1, 2, 3]) == True",
            "assert all_positive([1, -1, 3]) == False",
            "assert all_positive([0, 1, 2]) == False",
        ],
    },
    {
        "name": "any_negative",
        "correct_code": """\
def any_negative(lst):
    for num in lst:
        if num < 0:
            return True
    return False""",
        "tests": [
            "assert any_negative([1, -2, 3]) == True",
            "assert any_negative([1, 2, 3]) == False",
            "assert any_negative([-1]) == True",
        ],
    },
    {
        "name": "is_empty",
        "correct_code": """\
def is_empty(lst):
    if len(lst) == 0:
        return True
    return False""",
        "tests": [
            "assert is_empty([]) == True",
            "assert is_empty([1]) == False",
            "assert is_empty([1, 2]) == False",
        ],
    },
    {
        "name": "is_substring",
        "correct_code": """\
def is_substring(s, sub):
    if len(sub) > len(s):
        return False
    for i in range(len(s) - len(sub) + 1):
        if s[i:i + len(sub)] == sub:
            return True
    return False""",
        "tests": [
            "assert is_substring('hello world', 'world') == True",
            "assert is_substring('hello', 'xyz') == False",
            "assert is_substring('abc', 'abc') == True",
        ],
    },
    {
        "name": "is_leap_year",
        "correct_code": """\
def is_leap_year(year):
    if year % 400 == 0:
        return True
    if year % 100 == 0:
        return False
    if year % 4 == 0:
        return True
    return False""",
        "tests": [
            "assert is_leap_year(2000) == True",
            "assert is_leap_year(1900) == False",
            "assert is_leap_year(2024) == True",
        ],
    },
    {
        "name": "list_equals",
        "correct_code": """\
def list_equals(a, b):
    if len(a) != len(b):
        return False
    for i in range(len(a)):
        if a[i] != b[i]:
            return False
    return True""",
        "tests": [
            "assert list_equals([1, 2, 3], [1, 2, 3]) == True",
            "assert list_equals([1, 2], [1, 3]) == False",
            "assert list_equals([1], [1, 2]) == False",
        ],
    },
    {
        "name": "ends_with",
        "correct_code": """\
def ends_with(s, suffix):
    if len(suffix) > len(s):
        return False
    if suffix == '':
        return True
    return s[-len(suffix):] == suffix""",
        "tests": [
            "assert ends_with('hello', 'lo') == True",
            "assert ends_with('world', 'xyz') == False",
            "assert ends_with('abc', 'abc') == True",
        ],
    },
    {
        "name": "has_common_element",
        "correct_code": """\
def has_common_element(a, b):
    for item in a:
        if item in b:
            return True
    return False""",
        "tests": [
            "assert has_common_element([1, 2, 3], [3, 4, 5]) == True",
            "assert has_common_element([1, 2], [3, 4]) == False",
            "assert has_common_element([7], [7]) == True",
        ],
    },
    {
        "name": "is_strictly_increasing",
        "correct_code": """\
def is_strictly_increasing(lst):
    for i in range(len(lst) - 1):
        if lst[i] >= lst[i + 1]:
            return False
    return True""",
        "tests": [
            "assert is_strictly_increasing([1, 2, 3, 4]) == True",
            "assert is_strictly_increasing([1, 2, 2, 3]) == False",
            "assert is_strictly_increasing([3, 2, 1]) == False",
        ],
    },
    {
        "name": "is_valid_triangle",
        "correct_code": """\
def is_valid_triangle(a, b, c):
    if a + b > c and b + c > a and a + c > b:
        return True
    return False""",
        "tests": [
            "assert is_valid_triangle(3, 4, 5) == True",
            "assert is_valid_triangle(1, 2, 10) == False",
            "assert is_valid_triangle(5, 5, 5) == True",
        ],
    },
    {
        "name": "all_same",
        "correct_code": """\
def all_same(lst):
    if len(lst) == 0:
        return True
    first = lst[0]
    for item in lst:
        if item != first:
            return False
    return True""",
        "tests": [
            "assert all_same([1, 1, 1]) == True",
            "assert all_same([1, 2, 1]) == False",
            "assert all_same([]) == True",
        ],
    },

    # ── EXTRA: RANGE-HEAVY (targets off_by_one) ───────────────────────────────
    {
        "name": "sum_range",
        "correct_code": """\
def sum_range(n):
    total = 0
    for i in range(1, n + 1):
        total += i
    return total""",
        "tests": [
            "assert sum_range(5) == 15",
            "assert sum_range(1) == 1",
            "assert sum_range(10) == 55",
        ],
    },
    {
        "name": "count_up_to",
        "correct_code": """\
def count_up_to(n):
    result = []
    for i in range(1, n + 1):
        result.append(i)
    return result""",
        "tests": [
            "assert count_up_to(5) == [1, 2, 3, 4, 5]",
            "assert count_up_to(1) == [1]",
            "assert count_up_to(3) == [1, 2, 3]",
        ],
    },
    {
        "name": "squares_up_to",
        "correct_code": """\
def squares_up_to(n):
    result = []
    for i in range(1, n + 1):
        result.append(i * i)
    return result""",
        "tests": [
            "assert squares_up_to(4) == [1, 4, 9, 16]",
            "assert squares_up_to(1) == [1]",
            "assert squares_up_to(3) == [1, 4, 9]",
        ],
    },
    {
        "name": "sum_even_up_to",
        "correct_code": """\
def sum_even_up_to(n):
    total = 0
    for i in range(2, n + 1, 2):
        total += i
    return total""",
        "tests": [
            "assert sum_even_up_to(10) == 30",
            "assert sum_even_up_to(2) == 2",
            "assert sum_even_up_to(6) == 12",
        ],
    },
    {
        "name": "triangle_number",
        "correct_code": """\
def triangle_number(n):
    total = 0
    for i in range(1, n + 1):
        total += i
    return total""",
        "tests": [
            "assert triangle_number(4) == 10",
            "assert triangle_number(1) == 1",
            "assert triangle_number(5) == 15",
        ],
    },
    {
        "name": "digit_list",
        "correct_code": """\
def digit_list(n):
    digits = []
    n = abs(n)
    while n > 0:
        digits.append(n % 10)
        n //= 10
    digits.reverse()
    return digits""",
        "tests": [
            "assert digit_list(123) == [1, 2, 3]",
            "assert digit_list(9) == [9]",
            "assert digit_list(100) == [1, 0, 0]",
        ],
    },
    {
        "name": "repeat_list",
        "correct_code": """\
def repeat_list(lst, n):
    result = []
    for i in range(n):
        for item in lst:
            result.append(item)
    return result""",
        "tests": [
            "assert repeat_list([1, 2], 3) == [1, 2, 1, 2, 1, 2]",
            "assert repeat_list([5], 2) == [5, 5]",
            "assert repeat_list([1, 2, 3], 1) == [1, 2, 3]",
        ],
    },

    # ── EXTRA: MULTI-VARIABLE ARITHMETIC (targets swap_variable_reference) ────
    {
        "name": "subtract",
        "correct_code": """\
def subtract(a, b):
    return a - b""",
        "tests": [
            "assert subtract(10, 3) == 7",
            "assert subtract(0, 5) == -5",
            "assert subtract(7, 7) == 0",
        ],
    },
    {
        "name": "divide",
        "correct_code": """\
def divide(a, b):
    return a / b""",
        "tests": [
            "assert divide(10, 2) == 5.0",
            "assert divide(9, 3) == 3.0",
            "assert divide(1, 4) == 0.25",
        ],
    },
    {
        "name": "modulo",
        "correct_code": """\
def modulo(a, b):
    return a % b""",
        "tests": [
            "assert modulo(10, 3) == 1",
            "assert modulo(15, 5) == 0",
            "assert modulo(7, 4) == 3",
        ],
    },
    {
        "name": "hypotenuse",
        "correct_code": """\
def hypotenuse(a, b):
    return (a * a + b * b) ** 0.5""",
        "tests": [
            "assert hypotenuse(3, 4) == 5.0",
            "assert hypotenuse(5, 12) == 13.0",
            "assert hypotenuse(8, 6) == 10.0",
        ],
    },
    {
        "name": "area_rectangle",
        "correct_code": """\
def area_rectangle(width, height):
    return width * height""",
        "tests": [
            "assert area_rectangle(4, 5) == 20",
            "assert area_rectangle(3, 3) == 9",
            "assert area_rectangle(1, 7) == 7",
        ],
    },
    {
        "name": "bmi",
        "correct_code": """\
def bmi(weight, height):
    return weight / (height * height)""",
        "tests": [
            "assert round(bmi(70, 1.75), 2) == 22.86",
            "assert round(bmi(60, 1.60), 2) == 23.44",
            "assert round(bmi(90, 1.80), 2) == 27.78",
        ],
    },
    {
        "name": "weighted_average",
        "correct_code": """\
def weighted_average(value, weight, total_weight):
    return (value * weight) / total_weight""",
        "tests": [
            "assert weighted_average(80, 3, 5) == 48.0",
            "assert weighted_average(100, 1, 1) == 100.0",
            "assert weighted_average(50, 2, 4) == 25.0",
        ],
    },
    {
        "name": "range_of_list",
        "correct_code": """\
def range_of_list(lst):
    max_val = lst[0]
    min_val = lst[0]
    for num in lst:
        if num > max_val:
            max_val = num
        if num < min_val:
            min_val = num
    return max_val - min_val""",
        "tests": [
            "assert range_of_list([1, 5, 3, 9, 2]) == 8",
            "assert range_of_list([4, 4, 4]) == 0",
            "assert range_of_list([10, 1]) == 9",
        ],
    },

    # ── EXTRA: GENERAL (fills remaining bug types) ────────────────────────────
    {
        "name": "celsius_to_kelvin",
        "correct_code": """\
def celsius_to_kelvin(c):
    return c + 273.15""",
        "tests": [
            "assert celsius_to_kelvin(0) == 273.15",
            "assert celsius_to_kelvin(100) == 373.15",
            "assert celsius_to_kelvin(-273.15) == 0.0",
        ],
    },
    {
        "name": "simple_interest",
        "correct_code": """\
def simple_interest(principal, rate, time):
    return (principal * rate * time) / 100""",
        "tests": [
            "assert simple_interest(1000, 5, 2) == 100.0",
            "assert simple_interest(500, 10, 1) == 50.0",
            "assert simple_interest(200, 5, 3) == 30.0",
        ],
    },
    {
        "name": "perimeter_rectangle",
        "correct_code": """\
def perimeter_rectangle(width, height):
    return 2 * (width + height)""",
        "tests": [
            "assert perimeter_rectangle(4, 5) == 18",
            "assert perimeter_rectangle(3, 3) == 12",
            "assert perimeter_rectangle(1, 10) == 22",
        ],
    },
    {
        "name": "min_max_diff",
        "correct_code": """\
def min_max_diff(lst):
    max_val = lst[0]
    min_val = lst[0]
    for num in lst[1:]:
        if num > max_val:
            max_val = num
        if num < min_val:
            min_val = num
    return max_val - min_val""",
        "tests": [
            "assert min_max_diff([3, 1, 4, 1, 5]) == 4",
            "assert min_max_diff([7, 7]) == 0",
            "assert min_max_diff([10, 2, 8]) == 8",
        ],
    },
    {
        "name": "average_of_two",
        "correct_code": """\
def average_of_two(a, b):
    return (a + b) / 2""",
        "tests": [
            "assert average_of_two(4, 6) == 5.0",
            "assert average_of_two(0, 10) == 5.0",
            "assert average_of_two(3, 3) == 3.0",
        ],
    },
    {
        "name": "nth_power_sum",
        "correct_code": """\
def nth_power_sum(n):
    total = 0
    for i in range(1, n + 1):
        total += i * i
    return total""",
        "tests": [
            "assert nth_power_sum(3) == 14",
            "assert nth_power_sum(1) == 1",
            "assert nth_power_sum(4) == 30",
        ],
    },
    {
        "name": "count_in_range",
        "correct_code": """\
def count_in_range(lst, low, high):
    count = 0
    for num in lst:
        if low <= num <= high:
            count += 1
    return count""",
        "tests": [
            "assert count_in_range([1, 5, 3, 8, 2], 2, 5) == 3",
            "assert count_in_range([1, 2, 3], 5, 10) == 0",
            "assert count_in_range([5, 10, 15], 5, 10) == 2",
        ],
    },
    {
        "name": "zip_sum",
        "correct_code": """\
def zip_sum(a, b):
    result = []
    for i in range(len(a)):
        result.append(a[i] + b[i])
    return result""",
        "tests": [
            "assert zip_sum([1, 2, 3], [4, 5, 6]) == [5, 7, 9]",
            "assert zip_sum([0, 0], [1, 1]) == [1, 1]",
            "assert zip_sum([10], [5]) == [15]",
        ],
    },
    {
        "name": "moving_average",
        "correct_code": """\
def moving_average(lst, k):
    result = []
    for i in range(len(lst) - k + 1):
        window = lst[i:i + k]
        result.append(sum(window) / k)
    return result""",
        "tests": [
            "assert moving_average([1, 2, 3, 4, 5], 3) == [2.0, 3.0, 4.0]",
            "assert moving_average([1, 2, 3], 2) == [1.5, 2.5]",
            "assert moving_average([5, 5, 5], 3) == [5.0]",
        ],
    },
]

# ─────────────────────────────────────────────────────────────────────────────
# GENERATOR
# ─────────────────────────────────────────────────────────────────────────────

def generate(target: int = 300, seed: int = 42) -> list:
    """
    Generate a dataset with a mix of single and multi-bug examples.

    Bug count distribution (approximate):
      1 bug  — 40 %  (baseline difficulty, good for early training)
      2 bugs — 40 %  (medium difficulty)
      3 bugs — 20 %  (hard, agent must find and fix 3 separate issues)

    For each example we randomly pick how many bugs to inject, then randomly
    pick that many distinct bug types and call inject_multi_bug(). If fewer
    bugs actually applied (some types don't fit the function), we keep the
    example as long as at least one bug was injected and the tests break.
    """
    random.seed(seed)
    examples = []
    skipped_base = 0
    skipped_failed = 0

    BUG_COUNT_WEIGHTS = [0.40, 0.40, 0.20]

    funcs = list(BASE_FUNCTIONS)
    random.shuffle(funcs)

    for func in funcs:
        if len(examples) >= target:
            break

        correct_result = run_tests(func["correct_code"], func["tests"])
        if correct_result["pass_rate"] < 1.0:
            print(f"  ⚠  SKIP base '{func['name']}' — correct code fails its own tests")
            skipped_base += 1
            continue

        all_bug_types = list(range(8))
        tried = set()

        for _ in range(6):
            if len(examples) >= target:
                break

            n_bugs = random.choices([1, 2, 3], weights=BUG_COUNT_WEIGHTS)[0]
            combo = tuple(sorted(random.sample(all_bug_types, min(n_bugs, 8))))

            if combo in tried:
                continue
            tried.add(combo)

            buggy_code, applied_bugs, modified_lines = inject_multi_bug(
                func["correct_code"], list(combo)
            )

            if not applied_bugs:
                skipped_failed += 1
                continue

            buggy_result = run_tests(buggy_code, func["tests"])
            if buggy_result["pass_rate"] >= 1.0:
                skipped_failed += 1
                continue

            idx = len(examples) + 1
            example = {
                "id": f"{func['name']}_bugs{''.join(str(b) for b in applied_bugs)}_{idx:03d}",
                "function_name": func["name"],
                "bug_count": len(applied_bugs),
                "correct_code": func["correct_code"],
                "buggy_code": buggy_code,
                "test_code": "\n".join(func["tests"]),
                "bug_types": applied_bugs,
                "bug_type_names": [BUG_NAMES[b] for b in applied_bugs],
                "modified_lines": modified_lines,
                "error_line": get_error_line(buggy_code),
                "verified": {
                    "correct_pass_rate": correct_result["pass_rate"],
                    "buggy_pass_rate": buggy_result["pass_rate"],
                    "buggy_tests_failed": buggy_result["failed"],
                },
            }
            examples.append(example)
            bug_label = f"{len(applied_bugs)}bug{'s' if len(applied_bugs)>1 else ''}"
            print(f"  ✅ [{idx:>3}] {example['id']}  ({bug_label})")

    print(f"\n── Stats ────────────────────────────────")
    print(f"  Generated        : {len(examples)}")
    counts = {1: 0, 2: 0, 3: 0}
    for ex in examples:
        counts[min(ex['bug_count'], 3)] += 1
    print(f"  1-bug examples   : {counts[1]}")
    print(f"  2-bug examples   : {counts[2]}")
    print(f"  3-bug examples   : {counts[3]}")
    print(f"  Skipped          : {skipped_base + skipped_failed}")
    return examples


def save(examples: list):
    for ex in examples:
        path = EXAMPLES_DIR / f"{ex['id']}.json"
        with open(path, "w") as f:
            json.dump(ex, f, indent=2)

    type_counts = {BUG_NAMES[i]: 0 for i in range(8)}
    for ex in examples:
        for bt in ex["bug_types"]:
            type_counts[BUG_NAMES[bt]] += 1

    index = {
        "total": len(examples),
        "by_bug_count": {
            "1": sum(1 for e in examples if e["bug_count"] == 1),
            "2": sum(1 for e in examples if e["bug_count"] == 2),
            "3": sum(1 for e in examples if e["bug_count"] >= 3),
        },
        "bug_type_counts": type_counts,
        "function_counts": {},
        "ids": [e["id"] for e in examples],
    }
    for ex in examples:
        fn = ex["function_name"]
        index["function_counts"][fn] = index["function_counts"].get(fn, 0) + 1

    with open(SCRIPT_DIR / "dataset_index.json", "w") as f:
        json.dump(index, f, indent=2)

    print(f"\nSaved {len(examples)} examples to {EXAMPLES_DIR}")
    print(f"\nBug count distribution:")
    for k, v in index["by_bug_count"].items():
        print(f"  {k} bug(s): {v:>3}  {'█' * v}")
    print(f"\nBug type appearances:")
    for name, count in type_counts.items():
        print(f"  {name:<35} {count:>3}  {'█' * count}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BugForge Dataset Generator")
    parser.add_argument("--target", type=int, default=300, help="Target number of examples")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    args = parser.parse_args()

    print(f"BugForge Dataset Generator")
    print(f"Target: {args.target} examples  |  Seed: {args.seed}\n")
    examples = generate(target=args.target, seed=args.seed)
    save(examples)