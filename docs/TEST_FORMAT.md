# BugForge — Test Input Format

This document is the **source of truth** for how users write test cases that the RL agent will use to evaluate its fixes.

---

## Overview

When you submit buggy code to BugForge, you also provide test cases. The agent uses only **pass/fail signals** from these tests — it never sees the correct code. Your tests are its entire window into whether a fix worked.

**Good tests = better agent performance.** Weak or vague tests lead to the agent thinking a wrong fix was correct.

---

## The Format

Each test case is a **single Python `assert` statement on its own line.**

```
assert <function_call> == <expected_value>
```

### Rules

| Rule | Detail |
|------|--------|
| One `assert` per line | No multi-line expressions |
| Call your function by exactly the name it's defined with | If your function is `def my_sort(arr):`, call `my_sort(...)` |
| No imports | The agent runs your code; don't import external libraries |
| No helper functions in the test block | All setup must be in the test line itself |
| Minimum 2 tests, recommended 3–5 | More tests catch more bug types |

---

## Complete Examples

### Example 1 — Finding the Maximum

```python
# --- CODE ---
def find_max(lst):
    max_val = lst[0]
    for num in lst:
        if num > max_val:  # BUG: should be >
            max_val = num
    return max_val

# --- TESTS ---
assert find_max([3, 1, 4, 1, 5, 9]) == 9
assert find_max([1]) == 1
assert find_max([-3, -1, -2]) == -1
```

### Example 2 — Factorial

```python
# --- CODE ---
def factorial(n):
    result = 0          # BUG: should be 1
    for i in range(1, n + 1):
        result *= i
    return result

# --- TESTS ---
assert factorial(5) == 120
assert factorial(0) == 1
assert factorial(3) == 6
```

### Example 3 — Palindrome Check

```python
# --- CODE ---
def is_palindrome(s):
    left = 0
    right = len(s) - 1
    while left < right:
        if s[left] != s[right]:
            return True    # BUG: should be False
        left += 1
        right -= 1
    return False           # BUG: should be True

# --- TESTS ---
assert is_palindrome('racecar') == True
assert is_palindrome('hello') == False
assert is_palindrome('a') == True
```

### Example 4 — Binary Search

```python
# --- CODE ---
def binary_search(arr, target):
    left = 0
    right = len(arr) - 1
    while left <= right:
        mid = (left + right) // 2
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            left = mid - 1   # BUG: should be mid + 1
        else:
            right = mid - 1
    return -1

# --- TESTS ---
assert binary_search([1, 3, 5, 7, 9], 5) == 2
assert binary_search([1, 3, 5, 7, 9], 1) == 0
assert binary_search([1, 3, 5, 7, 9], 10) == -1
```

---

## Writing Effective Tests

### Cover the extremes, not just the middle

```python
# ❌ Weak — only one case, easy to pass by accident
assert find_max([3, 1, 4]) == 4

# ✅ Strong — covers edge cases the bug might miss
assert find_max([3, 1, 4, 1, 5, 9]) == 9    # general case
assert find_max([1]) == 1                     # single element
assert find_max([-3, -1, -2]) == -1          # all negatives
```

### Cover both True and False for boolean functions

```python
# ❌ Only tests the True path — a bug returning True always would pass
assert is_prime(7) == True

# ✅ Tests both paths
assert is_prime(7) == True
assert is_prime(4) == False
assert is_prime(1) == False
```

### For sorting/searching, test a case that's already in the right state

```python
assert is_sorted([1, 2, 3]) == True    # already sorted
assert is_sorted([3, 1, 2]) == False   # needs sorting
assert is_sorted([1]) == True          # single element edge case
```

### For off-by-one-prone functions, use small known values

```python
assert factorial(0) == 1    # boundary
assert factorial(1) == 1    # another boundary
assert factorial(5) == 120  # general case
```

---

## What to Avoid

### ❌ Assertions that only check a property, not the value

```python
# Bad — passes for any non-empty list return
assert len(bubble_sort([3, 1, 2])) == 3

# Good
assert bubble_sort([3, 1, 2]) == [1, 2, 3]
```

### ❌ Using `print` instead of `assert`

```python
# Bad — never fails, gives no signal
print(factorial(5))   # just prints, doesn't assert

# Good
assert factorial(5) == 120
```

### ❌ Tests that would pass even when the function does nothing

```python
# Bad — passes even if find_max always returns 0
assert find_max([0]) == 0

# Good
assert find_max([3, 1, 4]) == 4   # the max is not 0
```

### ❌ Multi-line or complex setup

```python
# Bad — not supported
result = binary_search([1,3,5], 5)
assert result == 2

# Good — single line
assert binary_search([1, 3, 5], 5) == 2
```

---

## Quick Reference Card

```
✅ assert my_func(input) == expected_output
✅ assert my_func(a, b, c) == result
✅ assert my_func([1,2,3]) == [3,2,1]
✅ assert my_func('hello') == True
✅ assert my_func(0) is None

❌ result = my_func(x)
❌ print(my_func(x))
❌ assert my_func(x)          # no comparison
❌ import something            # no imports in tests
❌ def helper(): ...           # no helper definitions
```

---

## How the Agent Uses Your Tests

At each step, the agent applies one of 8 fix actions to the code. After each action, it runs your test suite and receives:

- `pass_rate` — fraction of tests passing (0.0 to 1.0)
- `error_line` — line number if the code has a syntax error
- `timed_out` — whether the code took too long

The agent is rewarded for increasing the pass rate toward 1.0. It stops when all tests pass or when it has used its maximum number of attempts.

This means: **if your tests are too easy, the agent might stop early thinking the bug is fixed when it isn't.** Write tests that would only all pass on genuinely correct code.