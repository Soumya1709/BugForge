# BugForge — Bug Type Registry

This document defines the 8 bug types used in the dataset and as actions in the RL agent's action space.
 
The action IDs (0–7) must match exactly in both the dataset JSON and the DQN action space.**

---

## Action Space Summary

| ID | Name | AST Target | Mutation |
|----|------|-----------|----------|
| 0 | `swap_comparison_operator` | `Compare` node | Flip `>` ↔ `<`, `>=` ↔ `<=`, `==` ↔ `!=` |
| 1 | `off_by_one` | `Call` node (`range()`) | Shift stop argument by −1 or remove `+1` |
| 2 | `flip_boolean_return` | `Return` node | Swap `True` ↔ `False` in explicit return |
| 3 | `swap_variable_reference` | `BinOp` node | Swap left and right `Name` operands |
| 4 | `invert_conditional` | `If` node | Wrap `test` with `not (...)` |
| 5 | `wrong_initial_value` | `Assign` node | Flip `0` ↔ `1` in first numeric assignment |
| 6 | `wrong_arithmetic_operator` | `BinOp` / `AugAssign` | Swap `+` ↔ `-`, `*` ↔ `//` |
| 7 | `wrong_return_value` | `Return` node | Replace non-boolean return value with `None` |

---

## Detailed Descriptions

---

### 0 — `swap_comparison_operator`

**What it does:** Finds the first comparison in the function and flips the operator.

**Operator mappings:**

| Original | Becomes |
|----------|---------|
| `<` | `>` |
| `>` | `<` |
| `<=` | `>=` |
| `>=` | `<=` |
| `==` | `!=` |
| `!=` | `==` |

**Injected example:**
```python
# Correct
if arr[j] > arr[j + 1]:
    arr[j], arr[j + 1] = arr[j + 1], arr[j]

# Buggy (bug type 0)
if arr[j] < arr[j + 1]:     # < instead of >
    arr[j], arr[j + 1] = arr[j + 1], arr[j]
```

**Applies to:** Any function with a comparison (`<`, `>`, `==`, etc.). Very common — covers sorting, searching, min/max, prime checking, etc.

---

### 1 — `off_by_one`

**What it does:** Modifies the stop argument of the first `range()` call. Handles both `range(n)` → `range(n-1)` and `range(x, n+1)` → `range(x, n)`.

**Injected example:**
```python
# Correct
for i in range(1, n + 1):
    result *= i

# Buggy (bug type 1)
for i in range(1, n):        # n+1 changed to n — misses last iteration
    result *= i
```

**Applies to:** Functions with explicit `range()` calls where the stop value is a constant or `n ± 1` expression.

---

### 2 — `flip_boolean_return`

**What it does:** Finds the first explicit `return True` or `return False` and flips it.

**Injected example:**
```python
# Correct
if n % i == 0:
    return False
return True

# Buggy (bug type 2)
if n % i == 0:
    return True              # was False — now returns True on divisor found
return True
```

**Applies to:** Boolean-returning functions that explicitly write `return True` or `return False` (as opposed to `return x == y`).

---

### 3 — `swap_variable_reference`

**What it does:** Finds the first binary operation where both operands are different variable names, and swaps them.

**Injected example:**
```python
# Correct
return a - b

# Buggy (bug type 3)
return b - a                 # a and b swapped — wrong for non-commutative ops
```

```python
# Correct
return (a * b) // g

# Buggy (bug type 3)
return (b * a) // g          # swapped — same value for Mult but caught by other tests
```

**Applies to:** Functions with subtraction, division, modulo, or other non-commutative operations involving two named variables.

---

### 4 — `invert_conditional`

**What it does:** Wraps the test of the first `if` statement with `not (...)`, inverting its logic.

**Injected example:**
```python
# Correct
if value < low:
    return low

# Buggy (bug type 4)
if not (value < low):        # now returns low when value is NOT too small
    return low
```

**Applies to:** Any function containing an `if` statement. Very broad.

---

### 5 — `wrong_initial_value`

**What it does:** Finds the first assignment statement where the value is the integer `0` or `1`, and flips it.

**Operator mappings:**

| Original | Becomes |
|----------|---------|
| `= 0` | `= 1` |
| `= 1` | `= 0` |

**Injected example:**
```python
# Correct
result = 1
for i in range(1, n + 1):
    result *= i

# Buggy (bug type 5)
result = 0                   # starts at 0 — every product stays 0
for i in range(1, n + 1):
    result *= i
```

**Applies to:** Functions that initialize accumulators (`total = 0`, `count = 0`) or product variables (`result = 1`).

---

### 6 — `wrong_arithmetic_operator`

**What it does:** Finds the first arithmetic operation (either `BinOp` or augmented assignment `+=`, `*=`) and swaps the operator.

**Operator mappings:**

| Original | Becomes |
|----------|---------|
| `+` | `-` |
| `-` | `+` |
| `*` | `//` |
| `//` | `*` |

**Injected example:**
```python
# Correct
result *= base

# Buggy (bug type 6)
result //= base              # floor division instead of multiplication
```

```python
# Correct
total += num

# Buggy (bug type 6)
total -= num                 # subtracts instead of adds
```

**Applies to:** Functions with arithmetic operators — very common across math, list, and string functions.

---

### 7 — `wrong_return_value`

**What it does:** Finds the first `return` statement that returns a non-boolean, non-`None` value and replaces the return expression with `None`.

**Injected example:**
```python
# Correct
def find_max(lst):
    ...
    return max_val

# Buggy (bug type 7)
def find_max(lst):
    ...
    return None              # returns None instead of the computed value
```

```python
# Correct
def factorial(n):
    ...
    return result

# Buggy (bug type 7)
def factorial(n):
    ...
    return None
```

**Applies to:** Any function that returns a computed variable or expression (not a literal `True`/`False`, which is handled by bug type 2).

---

## No-Op Behaviour

When a fix action is applied to code that has no matching AST node, the action is a **no-op**:

- The code is returned unchanged
- `applied = False` is returned by `apply_fix()`
- The environment gives a small negative reward (`-0.5`) for wasted attempts
- The code state is **not updated** (the current code stays the same)

This is intentional — the agent must learn which actions are applicable in context.

---

## Dataset Coverage

Generated from `dataset/generate_dataset.py`. Each example is double-verified:

1. Correct code passes all tests (`pass_rate == 1.0`)
2. Buggy code fails at least one test (`pass_rate < 1.0`)

Examples where the injection produced no AST change, or where the bug didn't break any test, are discarded automatically.