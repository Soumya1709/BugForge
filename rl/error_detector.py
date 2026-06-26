import ast


class ErrorDetector:
    """
    Detects syntax errors in Python code and extracts
    useful debugging information for the RL agent.

    If the code parses successfully:
        error_line = -1

    If parsing fails:
        error_line = line number reported by Python
    """

    def detect_syntax_error(self, code):
        """
        Checks whether the code contains a syntax error.

        Parameters
        ----------
        code : str
            Python source code.

        Returns
        -------
        dict
            {
                "has_error": bool,
                "error_type": str | None,
                "error_line": int,
                "message": str | None,
                "offset": int | None,
                "error_text": str | None
            }
        """

        try:
            ast.parse(code)

            return {
                "has_error": False,
                "error_type": None,
                "error_line": -1,
                "message": None,
                "offset": None,
                "error_text": None
            }

        except SyntaxError as e:

            return {
                "has_error": True,
                "error_type": "SyntaxError",
                "error_line": e.lineno,
                "message": e.msg,
                "offset": e.offset,
                "error_text": e.text.strip() if e.text else None
            }

    def extract_error_line(self, harness_result):
        """
        Extract the error line from the test harness output.

        Parameters
        ----------
        harness_result : dict

        Expected format:
        {
            "pass_rate": float,
            "error_line": int,
            "timed_out": bool
        }

        Returns
        -------
        int
            Error line if available,
            otherwise -1.
        """

        return harness_result.get("error_line", -1)


if __name__ == "__main__":

    detector = ErrorDetector()

   

    good_code = """
def add(a, b):
    return a + b
"""

    print("=" * 60)
    print("VALID CODE")
    print("=" * 60)

    result = detector.detect_syntax_error(good_code)

    print(result)

   

    bad_code = """
def add(a, b)
    return a + b
"""

    print("\n" + "=" * 60)
    print("INVALID CODE")
    print("=" * 60)

    result = detector.detect_syntax_error(bad_code)

    print(result)

   

    harness_result = {
        "pass_rate": 0.75,
        "error_line": 12,
        "timed_out": False
    }

    print("\n" + "=" * 60)
    print("HARNESS RESULT")
    print("=" * 60)

    line = detector.extract_error_line(harness_result)

    print("Extracted Error Line:", line)