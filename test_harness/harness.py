import ast
import os
import subprocess
import sys
import tempfile
from typing import Optional
 
# Default timeout in seconds per test run
DEFAULT_TIMEOUT = 5
 
 
# ─────────────────────────────────────────────────────────────────────────────
# INTERNAL HELPERS
# ─────────────────────────────────────────────────────────────────────────────
 
def _get_error_line(source: str) -> Optional[int]:
    """Return the line number of a SyntaxError in source, or None."""
    try:
        ast.parse(source)
        return None
    except SyntaxError as e:
        return e.lineno
    except Exception:
        return None
 
 
def _count_asserts(test_code: str) -> int:
    """Count the number of assert lines in test_code."""
    return sum(
        1 for line in test_code.strip().splitlines()
        if line.strip().startswith("assert")
    )
 
 
def _build_runner_script(code: str, test_code: str) -> str:
    """
    Build a self-contained Python script that:
      1. Defines the function(s) from `code`
      2. Runs each assert individually in a try/except
      3. Prints "passed,failed" on the last line
    """
    test_lines = [
        line.strip()
        for line in test_code.strip().splitlines()
        if line.strip().startswith("assert")
    ]
 
    blocks = ""
    for line in test_lines:
        # Indent the assert inside a try block
        safe_line = line.replace("\\", "\\\\").replace('"', '\\"')
        blocks += f"""
try:
    {line}
    _passed += 1
except Exception as _e:
    _failed += 1
"""
 
    return f"""{code}
 
_passed = 0
_failed = 0
{blocks}
print(f"{{_passed}},{{_failed}}")
"""
 
 
# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────────────────────
 
def run_tests(
    code: str,
    test_code: str,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict:
    """
    Run `test_code` assert statements against `code` in an isolated subprocess.
 
    Args:
        code:      Python source defining the function(s) to test.
        test_code: One assert statement per line.
        timeout:   Seconds before the subprocess is killed (default: 5).
 
    Returns:
        Agreed contract dict (see module docstring).
    """
    # ── Pre-flight: syntax check ──────────────────────────────────────────────
    error_line = _get_error_line(code)
    total = _count_asserts(test_code)
 
    if error_line is not None:
        return {
            "passed": 0,
            "failed": total,
            "total": total,
            "pass_rate": 0.0,
            "timed_out": False,
            "error_line": error_line,
        }
 
    if total == 0:
        # No runnable tests — return a neutral result
        return {
            "passed": 0,
            "failed": 0,
            "total": 0,
            "pass_rate": 0.0,
            "timed_out": False,
            "error_line": None,
        }
 
    # ── Build and run the script ──────────────────────────────────────────────
    script = _build_runner_script(code, test_code)
    tmp_path = None
 
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".py",
            delete=False,
            encoding="utf-8",
        ) as f:
            f.write(script)
            tmp_path = f.name
 
        proc = subprocess.run(
            [sys.executable, tmp_path],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
 
        output = proc.stdout.strip()
        if "," in output:
            passed, failed = map(int, output.split(",", 1))
            passed = max(0, min(passed, total))
            failed = max(0, min(failed, total))
            return {
                "passed": passed,
                "failed": failed,
                "total": total,
                "pass_rate": passed / total,
                "timed_out": False,
                "error_line": None,
            }
 
        # Unexpected output — treat as all failed
        return {
            "passed": 0,
            "failed": total,
            "total": total,
            "pass_rate": 0.0,
            "timed_out": False,
            "error_line": None,
        }
 
    except subprocess.TimeoutExpired:
        return {
            "passed": 0,
            "failed": total,
            "total": total,
            "pass_rate": 0.0,
            "timed_out": True,
            "error_line": None,
        }
 
    except Exception:
        return {
            "passed": 0,
            "failed": total,
            "total": total,
            "pass_rate": 0.0,
            "timed_out": False,
            "error_line": None,
        }
 
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
 
 
def validate_test_code(test_code: str) -> dict:
    """
    Validate user-submitted test code before using it.
    Returns {"valid": bool, "issues": [str], "assert_count": int}
 
    Used by the UI to give early feedback before the agent starts.
    """
    issues = []
    lines = [l.strip() for l in test_code.strip().splitlines() if l.strip()]
    assert_lines = [l for l in lines if l.startswith("assert")]
 
    if len(assert_lines) == 0:
        issues.append("No assert statements found. Write at least one: assert my_func(input) == expected")
 
    if len(assert_lines) < 2:
        issues.append("Only 1 test found. Recommend at least 2–3 to catch different bug types.")
 
    for line in lines:
        if line.startswith("import ") or line.startswith("from "):
            issues.append(f"Imports are not allowed in test code: '{line}'")
        if line.startswith("print("):
            issues.append(f"Use assert instead of print: '{line}'")
 
    for line in assert_lines:
        if "==" not in line and " is " not in line and " in " not in line:
            issues.append(f"Assert has no comparison — it will always pass or always fail: '{line}'")
 
    try:
        ast.parse(test_code)
    except SyntaxError as e:
        issues.append(f"Syntax error in test code at line {e.lineno}: {e.msg}")
 
    return {
        "valid": len([i for i in issues if "Recommend" not in i]) == 0,
        "issues": issues,
        "assert_count": len(assert_lines),
    }