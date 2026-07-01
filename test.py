from test_harness.harness import _build_runner_script


from test_harness.harness import run_tests

code = """
def absolute_value(n):
    if not n < 0:
        return -n
    return n
"""

tests = """
assert absolute_value(-5) == 5
assert absolute_value(3) == 3
assert absolute_value(0) == 0
"""
print(_build_runner_script(code, tests))
result = run_tests(code, tests)

print(result)