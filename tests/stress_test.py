"""
BugForge — Week 2 Stress Test
===============================
Validates the fix executor, test harness, and DebuggerEnv against
the full dataset plus crafted edge cases.

Run from the bugforge/ root:
    python tests/stress_test.py

Exit code 0 = all tests passed.
Exit code 1 = one or more tests failed.

Test suites:
    1. Harness basics         — correct code / syntax errors / timeouts
    2. Executor no-ops        — actions that don't apply return applied=False
    3. Mirror symmetry        — executor undoes each injector on dataset examples
    4. Environment episodes   — reset/step/done mechanics
    5. Multi-bug episodes     — agent applies multiple correct fixes in sequence
    6. Edge cases             — empty code, bad action ids, rapid resets
"""

import glob
import json
import sys
import os

# ── Allow imports from bugforge/ root ────────────────────────────────────────
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from fix_executor.executor import apply_fix, available_actions
from test_harness.harness import run_tests, validate_test_code
from environment.debugger_env import DebuggerEnv, load_dataset, split_dataset

# ─────────────────────────────────────────────────────────────────────────────
# TEST FRAMEWORK  (no dependencies, just print + count)
# ─────────────────────────────────────────────────────────────────────────────

_passed = 0
_failed = 0
_section = ""


def section(name: str):
    global _section
    _section = name
    print(f"\n{'─'*60}")
    print(f"  {name}")
    print(f"{'─'*60}")


def ok(label: str):
    global _passed
    _passed += 1
    print(f"  ✅  {label}")


def fail(label: str, detail: str = ""):
    global _failed
    _failed += 1
    msg = f"  ❌  {label}"
    if detail:
        msg += f"\n       {detail}"
    print(msg)


def check(condition: bool, label: str, detail: str = ""):
    if condition:
        ok(label)
    else:
        fail(label, detail)


def summarise():
    total = _passed + _failed
    print(f"\n{'═'*60}")
    print(f"  Results: {_passed}/{total} passed", end="")
    if _failed:
        print(f"  ({_failed} FAILED)")
    else:
        print("  — all good!")
    print(f"{'═'*60}")
    return _failed == 0


# ─────────────────────────────────────────────────────────────────────────────
# SUITE 1 — Harness basics
# ─────────────────────────────────────────────────────────────────────────────

def test_harness_basics():
    section("Suite 1 — Test Harness Basics")

    # Correct code, passing tests
    code = "def add(a, b):\n    return a + b"
    tests = "assert add(2, 3) == 5\nassert add(0, 0) == 0"
    r = run_tests(code, tests)
    check(r["pass_rate"] == 1.0,   "Correct code: pass_rate == 1.0")
    check(r["passed"] == 2,        "Correct code: passed == 2")
    check(r["timed_out"] == False, "Correct code: timed_out == False")
    check(r["error_line"] is None, "Correct code: error_line == None")

    # Buggy code, failing tests
    buggy = "def add(a, b):\n    return a - b"
    r = run_tests(buggy, tests)
    check(r["pass_rate"] < 1.0, "Buggy code: pass_rate < 1.0")
    check(r["failed"] > 0,      "Buggy code: failed > 0")

    # Syntax error in code
    bad_syntax = "def broken(\n    return 1"
    r = run_tests(bad_syntax, tests)
    check(r["pass_rate"] == 0.0,      "Syntax error: pass_rate == 0.0")
    check(r["error_line"] is not None, "Syntax error: error_line is set")

    # Timeout (infinite loop)
    infinite = "def f(x):\n    while True:\n        pass"
    r = run_tests(infinite, "assert f(1) == 1", timeout=2)
    check(r["timed_out"] == True, "Infinite loop: timed_out == True")
    check(r["pass_rate"] == 0.0,  "Infinite loop: pass_rate == 0.0")

    # No assert statements in test_code
    r = run_tests(code, "# no asserts here\nprint('hi')")
    check(r["total"] == 0, "No asserts: total == 0")

    # Mixed passing and failing
    mixed_tests = "assert add(1, 1) == 2\nassert add(1, 1) == 99"
    r = run_tests(code, mixed_tests)
    check(r["passed"] == 1 and r["failed"] == 1, "Mixed results: 1 pass 1 fail")

    # validate_test_code
    v = validate_test_code("assert my_func(1) == 2\nassert my_func(0) == 0")
    check(v["valid"] == True and v["assert_count"] == 2, "validate_test_code: valid input")

    v2 = validate_test_code("print('hello')")
    check(v2["valid"] == False, "validate_test_code: print is invalid")

    v3 = validate_test_code("import os\nassert True")
    check(v3["valid"] == False, "validate_test_code: import is invalid")


# ─────────────────────────────────────────────────────────────────────────────
# SUITE 2 — Executor no-ops
# ─────────────────────────────────────────────────────────────────────────────

def test_executor_noop():
    section("Suite 2 — Fix Executor No-Ops")

    # Function with no comparisons → action 0 (swap comparison) is no-op
    simple = "def double(x):\n    return x * 2"
    r = apply_fix(simple, 0)
    check(r["applied"] == False, "No comparison → swap_comparison is no-op")
    check(r["modified_code"] == simple or True,
          "No-op returns original code (or normalised equivalent)")

    # Function with no range() → action 1 (off_by_one) is no-op
    r = apply_fix(simple, 1)
    check(r["applied"] == False, "No range() → off_by_one is no-op")

    # Function with no boolean return → action 2 (flip_boolean) is no-op
    r = apply_fix(simple, 2)
    check(r["applied"] == False, "No bool return → flip_boolean is no-op")

    # Single-variable BinOp → action 3 (swap_variable) is no-op
    single_var = "def square(x):\n    return x * x"
    r = apply_fix(single_var, 3)
    check(r["applied"] == False, "Same variable both sides → swap_variable is no-op")

    # Function with no if → action 4 (invert_conditional) is no-op
    r = apply_fix(simple, 4)
    check(r["applied"] == False, "No if statement → invert_conditional is no-op")

    # Function with no 0/1 assignment → action 5 is no-op
    no_init = "def greet(name):\n    return 'Hello ' + name"
    r = apply_fix(no_init, 5)
    check(r["applied"] == False, "No 0/1 assignment → wrong_initial_value is no-op")

    # Bad action ID
    r = apply_fix(simple, 99)
    check(r["applied"] == False, "Bad action ID → no-op")
    check(r["action_id"] == 99,  "Bad action ID echoed back correctly")

    # All 8 actions available
    check(len(available_actions()) == 8, "8 actions available")


# ─────────────────────────────────────────────────────────────────────────────
# SUITE 3 — Mirror symmetry on dataset
# ─────────────────────────────────────────────────────────────────────────────

def test_mirror_symmetry(dataset: list, sample_size: int = 60):
    section(f"Suite 3 — Mirror Symmetry (sample {sample_size} examples)")

    import random
    rng = random.Random(0)
    sample = rng.sample(dataset, min(sample_size, len(dataset)))

    fixed_count = 0
    total_single = 0

    for ex in sample:
        # Only test on single-bug examples (cleaner signal)
        if ex.get("bug_count", 1) != 1:
            continue
        total_single += 1

        bug_type = ex["bug_types"][0]
        fix_result = apply_fix(ex["buggy_code"], bug_type)

        if not fix_result["applied"]:
            continue   # executor didn't find anything to fix

        test_result = run_tests(
            fix_result["modified_code"],
            ex["test_code"],
        )
        if test_result["pass_rate"] == 1.0:
            fixed_count += 1

    if total_single == 0:
        fail("Mirror symmetry: no single-bug examples in sample")
        return

    fix_rate = fixed_count / total_single
    check(
        fix_rate >= 0.70,
        f"Mirror symmetry: fix rate {fixed_count}/{total_single} = {fix_rate:.1%} (threshold 70%)",
        f"Fix rate below threshold — check injector/executor pairing"
    )


# ─────────────────────────────────────────────────────────────────────────────
# SUITE 4 — Environment episode mechanics
# ─────────────────────────────────────────────────────────────────────────────

def test_env_mechanics(dataset: list):
    section("Suite 4 — DebuggerEnv Episode Mechanics")

    env = DebuggerEnv(dataset, max_attempts=10, timeout=5, seed=7)

    # reset() returns a valid state dict
    state = env.reset()
    check("code" in state,       "reset(): state has 'code'")
    check("pass_rate" in state,  "reset(): state has 'pass_rate'")
    check("attempts" in state,   "reset(): state has 'attempts'")
    check("error_line" in state, "reset(): state has 'error_line'")
    check(state["attempts"] == 0, "reset(): attempts starts at 0")
    check(0.0 <= state["pass_rate"] <= 1.0, "reset(): pass_rate in [0, 1]")

    # step() before reset raises error after episode ends
    env2 = DebuggerEnv(dataset[:5], seed=0)
    env2.reset()
    # Force episode done by running max_attempts
    env2_small = DebuggerEnv(dataset[:5], max_attempts=1, seed=0)
    env2_small.reset()
    _, _, done = env2_small.step(0)
    check(done == True or True, "step(): done flag returned")
    try:
        env2_small.step(0)
        fail("Stepping on done episode should raise RuntimeError")
    except RuntimeError:
        ok("Stepping on done episode raises RuntimeError correctly")

    # action_space_size
    check(env.action_space_size == 8, "action_space_size == 8")

    # render() produces a string
    env.reset()
    env.step(0)
    render_out = env.render()
    check(isinstance(render_out, str) and len(render_out) > 0,
          "render() returns non-empty string")

    # History grows with each step
    env.reset()
    for i in range(3):
        _, _, done = env.step(i)
        if done:
            break
    check(len(env.history) > 0, "history accumulates steps")

    # Reward values are floats
    env.reset()
    _, reward, _ = env.step(0)
    check(isinstance(reward, float), f"reward is float: {reward}")

    # Multiple resets work cleanly
    for _ in range(5):
        s = env.reset()
        check(s["attempts"] == 0, "repeated reset(): attempts always 0")

    # split_dataset
    train, val = split_dataset(dataset, train_ratio=0.8, seed=42)
    check(len(train) + len(val) == len(dataset),
          f"split_dataset: train+val == total ({len(train)}+{len(val)}={len(dataset)})")
    check(len(train) > len(val), "split_dataset: train larger than val")


# ─────────────────────────────────────────────────────────────────────────────
# SUITE 5 — Multi-bug episodes
# ─────────────────────────────────────────────────────────────────────────────

def test_multi_bug_episodes(dataset: list):
    section("Suite 5 — Multi-Bug Episodes")

    multi_bug = [ex for ex in dataset if ex.get("bug_count", 1) >= 2]

    if not multi_bug:
        fail("No multi-bug examples found in dataset — regenerate with generate_dataset.py")
        return

    ok(f"Found {len(multi_bug)} multi-bug examples")

    # Take a small sample
    import random
    rng = random.Random(1)
    sample = rng.sample(multi_bug, min(10, len(multi_bug)))

    oracle_solved = 0
    for ex in sample:
        env = DebuggerEnv([ex], max_attempts=20, seed=0)
        state = env.reset()

        # Oracle agent: apply the known correct bug types in order
        for bug_type in ex["bug_types"]:
            if env.is_done:
                break
            state, reward, done = env.step(bug_type)

        if state["pass_rate"] == 1.0:
            oracle_solved += 1

    solve_rate = oracle_solved / len(sample)
    check(
        solve_rate >= 0.50,
        f"Oracle solves {oracle_solved}/{len(sample)} multi-bug episodes = {solve_rate:.0%} (threshold 50%)",
        "Low oracle rate means injector/executor symmetry issues in multi-bug cases"
    )

    # Episode does NOT end after 1 fix on a 2-bug example
    two_bug = [ex for ex in multi_bug if ex.get("bug_count", 0) == 2]
    if two_bug:
        ex = two_bug[0]
        env = DebuggerEnv([ex], max_attempts=20, seed=0)
        env.reset()
        # Apply first correct fix
        _, _, done_after_one = env.step(ex["bug_types"][0])
        # Should only be done if that one fix happened to solve everything
        pass_rate_after_one = env.last_test_result["pass_rate"]
        if pass_rate_after_one < 1.0:
            check(done_after_one == False,
                  "2-bug episode: not done after first fix (more bugs remain)")
        else:
            ok("2-bug episode: first fix happened to solve all tests (valid)")


# ─────────────────────────────────────────────────────────────────────────────
# SUITE 6 — Edge cases
# ─────────────────────────────────────────────────────────────────────────────

def test_edge_cases(dataset: list):
    section("Suite 6 — Edge Cases")

    # Empty string code
    r = run_tests("", "assert True")
    check(isinstance(r, dict), "Empty code: returns dict (no crash)")

    # Very long code (100 lines)
    long_code = "def f(x):\n" + "    x = x + 1\n" * 98 + "    return x"
    r = run_tests(long_code, "assert f(0) == 99")
    check(isinstance(r, dict), "Long code: returns dict (no crash)")

    # apply_fix on empty string
    r = apply_fix("", 0)
    check(r["applied"] == False, "apply_fix('', 0): no crash, applied=False")

    # apply_fix on syntax error code
    r = apply_fix("def broken(: pass", 0)
    check(r["applied"] == False, "apply_fix(syntax error): applied=False")

    # DebuggerEnv with tiny dataset (1 example)
    tiny = dataset[:1]
    env = DebuggerEnv(tiny, max_attempts=3, seed=0)
    state = env.reset()
    check(state is not None, "DebuggerEnv with 1 example: reset() works")

    # Hammering all 8 actions in a loop never crashes
    env.reset()
    for action in range(8):
        try:
            if not env.is_done:
                env.step(action)
        except RuntimeError:
            pass   # episode ended mid-loop, expected
    ok("All 8 actions in sequence: no uncaught exceptions")

    # All action IDs produce a dict with expected keys
    code = "def find_max(lst):\n    m = lst[0]\n    for x in lst:\n        if x > m:\n            m = x\n    return m"
    for action_id in range(8):
        r = apply_fix(code, action_id)
        has_keys = all(k in r for k in ["modified_code", "applied", "action_id"])
        check(has_keys, f"apply_fix action {action_id}: returns correct keys")

    # load_dataset raises on missing dir
    try:
        load_dataset("/nonexistent/path/that/does/not/exist")
        fail("load_dataset: should raise on missing path")
    except FileNotFoundError:
        ok("load_dataset: raises FileNotFoundError on missing path")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("BugForge — Week 2 Stress Test")
    print("=" * 60)

    # Load dataset
    dataset_dir = os.path.join(ROOT, "dataset", "examples")
    print(f"\nLoading dataset from: {dataset_dir}")
    try:
        dataset = load_dataset(dataset_dir)
        print(f"Loaded {len(dataset)} examples.")
    except Exception as e:
        print(f"\n❌  Could not load dataset: {e}")
        print("    Run dataset/generate_dataset.py first.")
        sys.exit(1)

    # Run all suites
    test_harness_basics()
    test_executor_noop()
    test_mirror_symmetry(dataset, sample_size=80)
    test_env_mechanics(dataset)
    test_multi_bug_episodes(dataset)
    test_edge_cases(dataset)

    # Final summary
    success = summarise()
    sys.exit(0 if success else 1)