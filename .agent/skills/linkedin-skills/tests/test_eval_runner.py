"""Offline tests for evaluation-runner result reporting."""

import contextlib
import io
import sys
import unittest
from unittest import mock

import evals.run_evals as runner


def make_case(passed):
    def build():
        def grade(output):
            return passed, "test grader detail"
        return "test prompt", grade

    return ("test case", build)


class EvaluationRunnerReportingTests(unittest.TestCase):
    def run_runner(self, cases, ask_results):
        output = io.StringIO()
        with (
            mock.patch.object(runner, "CASES", cases),
            mock.patch.object(runner, "ask", side_effect=ask_results),
            mock.patch.object(sys, "argv", ["run_evals.py"]),
            contextlib.redirect_stdout(output),
        ):
            exit_code = runner.main()

        return exit_code, output.getvalue()

    def test_all_cases_pass_returns_zero(self):
        exit_code, output = self.run_runner(
            {"passing": make_case(True)},
            [("good answer", "")],
        )

        self.assertEqual(exit_code, 0)
        self.assertIn("All cases passed", output)

    def test_graded_failure_returns_nonzero(self):
        exit_code, output = self.run_runner(
            {"failing": make_case(False)},
            [("bad answer", "")],
        )

        self.assertNotEqual(exit_code, 0)
        self.assertIn("1 case(s) failed", output)

    def test_error_or_skip_returns_nonzero_and_is_not_all_passed(self):
        exit_code, output = self.run_runner(
            {"unavailable": make_case(True)},
            [("", "the claude CLI is not on PATH")],
        )

        self.assertNotEqual(exit_code, 0)
        self.assertIn("1 case(s) skipped/error", output)
        self.assertNotIn("All cases passed", output)

    def test_failure_and_error_are_both_reported(self):
        exit_code, output = self.run_runner(
            {
                "failing": make_case(False),
                "unavailable": make_case(True),
            },
            [
                ("bad answer", ""),
                ("", "simulated timeout"),
            ],
        )

        self.assertNotEqual(exit_code, 0)
        self.assertIn("1 case(s) failed", output)
        self.assertIn("1 case(s) skipped/error", output)


if __name__ == "__main__":
    unittest.main()
