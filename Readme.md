# BugForge 

An RL agent that learns to debug arbitrary Python code using only test pass/fail signals — no correct code, no diffs, no hints.

> **Status:** Active development 
> **Team:** [Soumya Sinha — RL Brain] · [Tejaswi Raj — Environment & Data]

---

## What Is This?

BugForge is a Deep Q-Network (DQN) agent that debugs buggy Python functions. Given a function and a set of `assert`-based tests, the agent:

1. Encodes the code using a CodeBERT-based state representation
2. Chooses one of 8 fix actions from a fixed action space (e.g. "swap comparison operator", "fix off-by-one")
3. Applies the action to the code via AST transformation
4. Runs the test suite in a sandboxed subprocess
5. Gets rewarded when more tests pass
6. Repeats until all tests pass or the attempt limit is hit

The agent never sees the correct version of the code. Its only signal is whether tests pass or fail.

---

## Project Structure

```
bugforge/
├── dataset/
│   ├── generate_dataset.py     ← builds the 300-example training set
│   ├── dataset_index.json      ← generated index with bug type distribution
│   └── examples/               ← 300 verified JSON examples (generated)
│       ├── bubble_sort_bug0_001.json
│       └── ...
│
├── docs/
│   ├── TEST_FORMAT.md          ← how to write test cases (user-facing)
│   └── BUG_TYPES.md            ← action space contract (shared Person A ↔ B)
│
├── environment/                ← [TODO — Week 2]
│   └── debugger_env.py         ← OpenAI Gym-style environment class
│
├── fix_executor/               ← [TODO — Week 2]
│   └── executor.py             ← AST-based fix action executor
│
├── test_harness/               ← [TODO — Week 2]
│   └── harness.py              ← subprocess-isolated test runner
│
├── agent/                      ← [TODO — Person A, Week 2]
│   ├── encoder.py              ← CodeBERT state encoder
│   ├── dqn.py                  ← Q-network + replay buffer
│   └── train.py                ← training loop
│
└── ui/                         ← [TODO — Week 3]
    └── app.py                  ← Streamlit interface
```

---

## The Dataset

**300 verified buggy/correct Python code pairs** across 90 unique functions, with 8 bug types.

Each example is a JSON file:

```json
{
  "id": "bubble_sort_bug0_088",
  "function_name": "bubble_sort",
  "correct_code": "def bubble_sort(arr):\n    ...",
  "buggy_code": "def bubble_sort(arr):\n    ...",
  "test_code": "assert bubble_sort([64, 34, 25, 12, 22]) == [12, 22, 25, 34, 64]\nassert bubble_sort([3, 1, 2]) == [1, 2, 3]\nassert bubble_sort([1, 2, 3]) == [1, 2, 3]",
  "bug_type": 0,
  "bug_type_name": "swap_comparison_operator",
  "error_line": null,
  "verified": {
    "correct_pass_rate": 1.0,
    "buggy_pass_rate": 0.0,
    "buggy_tests_failed": 3
  }
}
```

### Bug Type Distribution

| ID | Bug Type | Count |
|----|----------|-------|
| 0 | swap_comparison_operator | 55 |
| 1 | off_by_one | 15 |
| 2 | flip_boolean_return | 17 |
| 3 | swap_variable_reference | 13 |
| 4 | invert_conditional | 53 |
| 5 | wrong_initial_value | 25 |
| 6 | wrong_arithmetic_operator | 53 |
| 7 | wrong_return_value | 69 |
| | **Total** | **300** |

### Verification Guarantee

Every example was double-verified by the generator:

- The **correct code** was run against its tests → all tests must pass
- The **buggy code** was run against the same tests → at least one test must fail

Any (function, bug type) pair that didn't meet both conditions was discarded automatically.

### Function Categories

Functions cover: sorting, searching, math, string operations, list operations, boolean checks, number systems, and conditionals. Naming styles are deliberately varied (verbose: `calculate_factorial`, terse: `fact`, single-letter params: `f(x, y)`) so the CodeBERT encoder sees structural patterns, not naming patterns.

---

## The 8 Fix Actions

The agent's action space is defined in [`docs/BUG_TYPES.md`](docs/BUG_TYPES.md).

Quick summary:

| ID | Action |
|----|--------|
| 0 | Swap comparison operator (`>` ↔ `<`, `>=` ↔ `<=`, etc.) |
| 1 | Off-by-one fix in `range()` stop argument |
| 2 | Flip boolean return (`True` ↔ `False`) |
| 3 | Swap variable reference (swap left/right of a BinOp) |
| 4 | Invert conditional (`if x` → `if not x`) |
| 5 | Fix initial value (`0` ↔ `1`) |
| 6 | Fix arithmetic operator (`+` ↔ `-`, `*` ↔ `//`) |
| 7 | Fix return value (restore correct return expression) |

---

## Test Input Format

See [`docs/TEST_FORMAT.md`](docs/TEST_FORMAT.md) for the complete user guide.

**Quick summary:** One `assert` statement per line. Call your function by the name it's defined with. No imports, no helpers, minimum 2 tests.

```python
assert my_function(input) == expected_output
assert my_function(edge_case) == expected_output
assert my_function(another_case) == expected_output
```

---

## Setup

**Requirements:** Python 3.9+ (uses `ast.unparse`)

```bash
git clone <repo-url>
cd bugforge
```

No external dependencies are needed for the dataset generator — it uses only the standard library.

**To regenerate the dataset:**

```bash
cd dataset
python generate_dataset.py               # generates 300 examples (default)
python generate_dataset.py --target 150  # smaller run
python generate_dataset.py --seed 99     # different random seed
```

**Coming in Week 2** (requires installation):

```bash
# pip install torch transformers gym
```

---

## Architecture Overview

```
User input (buggy code + tests)
        │
        ▼
┌───────────────────┐
│   Test Harness    │  Runs tests in subprocess, returns pass/fail counts
└───────────┬───────┘
            │ test result dict
            ▼
┌───────────────────┐
│  State Encoder    │  CodeBERT → 768-dim embedding + pass_rate + error_line + attempts
│  [Person A]       │  → 771-dim state vector
└───────────┬───────┘
            │ state vector
            ▼
┌───────────────────┐
│   DQN Agent       │  Q(state, action) for 8 actions, ε-greedy, replay buffer
│   [Person A]      │
└───────────┬───────┘
            │ action_id (0–7)
            ▼
┌───────────────────┐
│  Fix Executor     │  AST transformer applies fix action to current code
│  [Person B]       │
└───────────┬───────┘
            │ modified code
            ▼
┌───────────────────┐
│  DebuggerEnv      │  Gym-style reset/step, tracks attempts, computes reward
│  [Person B]       │
└───────────────────┘
```

### Reward Structure

| Outcome | Reward |
|---------|--------|
| All tests pass | `+10.0` |
| Partial improvement (some tests now pass) | `+1.0` |
| No improvement | `-0.5` |
| No-op (action didn't apply) | `-0.5` |
| Timeout | `-1.0` |

---

## Team

| Person | Role | Owns |
|--------|------|------|
| Soumya Sinha | RL Brain | `agent/encoder.py`, `agent/dqn.py`, `agent/train.py`, evaluation suite |
| Tejaswi Raj | Environment & Data | `dataset/`, `fix_executor/`, `test_harness/`, `environment/`, `ui/` |

---

## Limitations

- **Fixed action space:** The agent can only apply predefined fix patterns. Novel bugs outside the 8 types can't be fixed.
- **Single-bug assumption:** Each training example has exactly one injected bug. Real code often has multiple bugs.
- **Short functions only:** The dataset consists of short, self-contained functions. Complex multi-function code is out of scope.
- **Python only:** The AST tooling, test harness, and encoder are all Python-specific.
- **No loop learning:** The agent does not maintain memory across separate submissions.

---

## License

MIT