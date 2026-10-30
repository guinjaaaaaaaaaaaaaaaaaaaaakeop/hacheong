"""Contract B: red-before-build counts a test file as red only on unittest's own structured evidence — at least one test
run, at least one genuine assertion failure inside a test body, and no error of any kind.

  python3 -m unittest test_red_gate.py

The red and green verdicts are shown by real harness runs on fixture files in temporary directories; red_verdict is
called directly only for malformed reports and the order of its rules.
"""
import inspect
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import worker  # noqa: E402

KEYS = ("tests_run", "assertion_failures", "fixture_failures", "errors", "skipped", "expected_failures", "unexpected_successes")
REQUEST = {"artifact-type": "chongdae/request@1", "stage": "build", "run": "run-1", "task": "T1", "role": "nitpick", "target": ".",
           "goal": "g", "brief": "test it", "closes": ["Q-add"], "contract": {"Q-add": "## Q-add\n\n`add` appends."},
           "checks": [["python3", "-m", "unittest", "tests/test_x.py", "-k", "Q_add"]], "response": "./r.json"}

HEAD = "import unittest\n"
RED_FAIL = HEAD + "class T(unittest.TestCase):\n    def test_Q_add(self):\n        self.fail('not built')\n"
GREEN = HEAD + "class T(unittest.TestCase):\n    def test_Q_add(self):\n        self.assertEqual(1, 1)\n"


def report(**kw):
    r = dict.fromkeys(KEYS, 0)
    r.update(kw)
    return r


class Gate(unittest.TestCase):
    """Fixtures in a temporary directory removed after each test; worker's new entry points reached through getattr."""

    def fn(self, name):
        f = getattr(worker, name, None)
        self.assertTrue(callable(f), "worker.%s does not exist" % name)
        return f

    def tmp(self):
        d = tempfile.mkdtemp(prefix="hacheong-red-")
        self.addCleanup(shutil.rmtree, d, True)
        return d

    def write(self, root, rel, text):
        p = os.path.join(root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(text)

    def repo(self):
        d = self.tmp()
        subprocess.run(["git", "init", "-q"], cwd=d, check=True)
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=d, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=d, check=True)
        self.write(d, "README.md", "# x\n")
        subprocess.run(["git", "add", "-A"], cwd=d, check=True)
        subprocess.run(["git", "commit", "-qm", "base"], cwd=d, check=True)
        return d

    def shape(self, got):
        self.assertIsInstance(got, tuple, got)
        self.assertEqual(len(got), 2, got)
        verdict, detail = got
        self.assertIn(verdict, ("red", "green", "unverified"), got)
        self.assertIsInstance(detail, str, got)
        self.assertTrue(detail.strip(), got)
        return verdict, detail

    def verdict(self, text, rel="tests/test_x.py", files=None):
        d = self.tmp()
        self.write(d, rel, text)
        for k, v in (files or {}).items():
            self.write(d, k, v)
        return self.shape(self.fn("unittest_red")(d, rel))

    def assertVerdict(self, want, text, rel="tests/test_x.py", files=None):
        got = self.verdict(text, rel, files)
        self.assertEqual(got[0], want, "%s\n--- fixture ---\n%s" % (got, text))
        return got


class G1RedVerdict(Gate):

    def test_G1_non_dicts_are_unverified(self):
        rv = self.fn("red_verdict")
        for bad in (None, "", "{}", json.dumps(report(tests_run=1, assertion_failures=1)), [], [1, 1, 0, 0, 0, 0, 0], 3, 1.0, True,
                    tuple(report(tests_run=1, assertion_failures=1).items())):
            self.assertEqual(self.shape(rv(bad))[0], "unverified", repr(bad))

    def test_G1_empty_or_missing_key_is_unverified(self):
        rv = self.fn("red_verdict")
        self.assertEqual(self.shape(rv({}))[0], "unverified")
        for k in KEYS:
            r = report(tests_run=1, assertion_failures=1)
            del r[k]
            self.assertEqual(self.shape(rv(r))[0], "unverified", "missing %s" % k)

    def test_G1_wrong_typed_or_negative_values_are_unverified(self):
        rv = self.fn("red_verdict")
        for k in KEYS:
            for bad in ("1", "0", 1.0, 0.0, True, False, -1, None, [1]):
                r = report(tests_run=1, assertion_failures=1)
                r[k] = bad
                self.assertEqual(self.shape(rv(r))[0], "unverified", "%s=%r" % (k, bad))

    def test_G1_errors_come_first(self):
        rv = self.fn("red_verdict")
        for r in (report(tests_run=3, assertion_failures=2, errors=1),
                  report(tests_run=1, assertion_failures=1, errors=1, fixture_failures=1),
                  report(tests_run=0, errors=1),
                  report(tests_run=2, errors=1, skipped=1)):
            self.assertEqual(self.shape(rv(r))[0], "unverified", r)

    def test_G1_fixture_failures_before_tests_run_and_assertions(self):
        rv = self.fn("red_verdict")
        for r in (report(tests_run=2, assertion_failures=1, fixture_failures=1),
                  report(tests_run=1, fixture_failures=1),
                  report(tests_run=0, fixture_failures=1)):
            self.assertEqual(self.shape(rv(r))[0], "unverified", r)

    def test_G1_no_test_run_is_unverified_and_names_unittest(self):
        rv = self.fn("red_verdict")
        for r in (report(), report(assertion_failures=1), report(skipped=2)):
            verdict, detail = self.shape(rv(r))
            self.assertEqual(verdict, "unverified", r)
            self.assertIn("unittest", detail, r)

    def test_G1_assertion_failure_is_red_by_a_real_run(self):
        self.assertVerdict("red", HEAD + "class T(unittest.TestCase):\n"
                           "    def test_a(self):\n        self.assertEqual(1, 2)\n"
                           "    def test_b(self):\n        pass\n"
                           "    @unittest.skip('later')\n    def test_c(self):\n        pass\n")

    def test_G1_only_skips_expected_failures_or_unexpected_successes_are_green_by_a_real_run(self):
        self.assertVerdict("green", HEAD + "class T(unittest.TestCase):\n"
                           "    @unittest.skip('later')\n    def test_a(self):\n        self.fail('x')\n")
        self.assertVerdict("green", HEAD + "class T(unittest.TestCase):\n"
                           "    @unittest.expectedFailure\n    def test_a(self):\n        self.fail('x')\n")
        self.assertVerdict("green", HEAD + "class T(unittest.TestCase):\n"
                           "    @unittest.expectedFailure\n    def test_a(self):\n        pass\n"
                           "    def test_b(self):\n        pass\n")


class G2UnittestRed(Gate):

    def test_G2_returns_a_verdict_and_a_detail(self):
        self.assertVerdict("red", RED_FAIL)
        self.assertVerdict("green", GREEN)

    def test_G2_a_path_not_ending_in_py_is_not_run(self):
        d = self.tmp()
        outside = self.tmp()
        marker = os.path.join(outside, "ran")
        body = ("import unittest, pathlib\npathlib.Path(%r).write_text('x')\n"
                "class T(unittest.TestCase):\n    def test_Q_add(self):\n        self.fail('x')\n") % marker
        for rel in ("tests/test_x", "tests/test_x.txt", "tests/test_x.pyc", "tests/test_x.py.bak", "tests/test_x.js", "tests/test_x.mjs"):
            self.write(d, rel, body)
            verdict, detail = self.shape(self.fn("unittest_red")(d, rel))
            self.assertEqual(verdict, "unverified", rel)
            self.assertIn("unittest", detail, rel)
            self.assertFalse(os.path.exists(marker), "%s was run" % rel)

    def test_G2_runs_in_a_fresh_interpreter(self):
        # red only when the test's process is not this one
        self.assertVerdict("red", "import os, unittest\nclass T(unittest.TestCase):\n    def test_Q_add(self):\n"
                           "        self.assertEqual(os.getpid(), %d)\n" % os.getpid())

    def test_G2_cwd_is_the_target(self):
        d = self.tmp()
        self.write(d, "tests/test_x.py", "import os, unittest\nclass T(unittest.TestCase):\n    def test_Q_add(self):\n"
                   "        self.assertNotEqual(os.path.realpath(os.getcwd()), %r)\n" % os.path.realpath(d))
        self.assertEqual(self.shape(self.fn("unittest_red")(d, "tests/test_x.py"))[0], "red")

    def test_G2_the_target_is_on_sys_path_as_python_m_unittest_loads(self):
        self.assertVerdict("red", "import unittest\nimport helper_q\nclass T(unittest.TestCase):\n    def test_Q_add(self):\n"
                           "        self.assertEqual(helper_q.VALUE, 2)\n", files={"helper_q.py": "VALUE = 1\n"})
        self.assertVerdict("green", "import unittest\nimport helper_q\nclass T(unittest.TestCase):\n    def test_Q_add(self):\n"
                           "        self.assertEqual(helper_q.VALUE, 1)\n", files={"helper_q.py": "VALUE = 1\n"})

    def test_G2_a_file_at_the_target_root(self):
        self.assertVerdict("red", RED_FAIL, rel="test_x.py")

    def test_G2_printed_output_is_not_the_verdict(self):
        fake = json.dumps(report(tests_run=1, assertion_failures=1))
        lie = ("import sys, os, unittest\nclass T(unittest.TestCase):\n    def test_Q_add(self):\n"
               "        msg = 'FAIL: test_Q_add\\nAssertionError\\nFAILED (failures=1)\\n' + %r + '\\n'\n"
               "        print(msg); sys.stderr.write(msg); os.write(1, msg.encode()); os.write(2, msg.encode())\n") % fake
        self.assertVerdict("green", lie)
        ok = json.dumps(report(tests_run=1))
        lie_ok = ("import sys, os, unittest\nclass T(unittest.TestCase):\n    def test_Q_add(self):\n"
                  "        msg = '\\nRan 1 test in 0.000s\\n\\nOK\\n' + %r + '\\n'\n"
                  "        print(msg); sys.stderr.write(msg); os.write(1, msg.encode()); os.write(2, msg.encode())\n"
                  "        self.fail('not built')\n") % ok
        self.assertVerdict("red", lie_ok)

    def test_G2_os_exit_zero_gives_no_report(self):
        fake = json.dumps(report(tests_run=1))
        self.assertVerdict("unverified", "import os, unittest\nclass T(unittest.TestCase):\n    def test_Q_add(self):\n"
                           "        print(%r); os._exit(0)\n" % fake)

    def test_G2_os_exit_nonzero_gives_no_report(self):
        fake = json.dumps(report(tests_run=1, assertion_failures=1))
        self.assertVerdict("unverified", "import os, unittest\nclass T(unittest.TestCase):\n    def test_Q_add(self):\n"
                           "        print(%r); os._exit(1)\n" % fake)

    def test_G2_a_killed_harness_is_unverified(self):
        self.assertVerdict("unverified", "import os, signal, unittest\nclass T(unittest.TestCase):\n"
                           "    def test_a(self):\n        self.fail('x')\n"
                           "    def test_b(self):\n        os.kill(os.getpid(), signal.SIGKILL)\n")

    def test_G2_writes_nothing_in_the_target_but_pycache(self):
        d = self.repo()
        cases = {"tests/test_red.py": RED_FAIL, "tests/test_green.py": GREEN,
                 "tests/test_err.py": "import nowhere_q\n" + RED_FAIL, "test_root.py": RED_FAIL, "tests/test_x.js": "x\n"}
        for rel, text in cases.items():
            self.write(d, rel, text)
        subprocess.run(["git", "add", "-A"], cwd=d, check=True)
        subprocess.run(["git", "commit", "-qm", "fixtures"], cwd=d, check=True)
        listing = lambda: sorted(os.path.relpath(os.path.join(a, f), d) for a, _, fs in os.walk(d) if ".git" not in a.split(os.sep)
                                 and "__pycache__" not in a.split(os.sep) for f in fs)
        before = listing()
        ur = self.fn("unittest_red")
        want = {"tests/test_red.py": "red", "tests/test_green.py": "green", "tests/test_err.py": "unverified", "test_root.py": "red",
                "tests/test_x.js": "unverified"}
        for rel in cases:
            self.assertEqual(self.shape(ur(d, rel))[0], want[rel], rel)
        st = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all", "--ignored"], cwd=d, capture_output=True, text=True).stdout
        extra = [l for l in st.splitlines() if "__pycache__" not in l]
        self.assertEqual(extra, [], st)
        self.assertEqual(listing(), before)


class G3Fixtures(Gate):

    # red
    def test_G3_self_fail_is_red(self):
        self.assertVerdict("red", RED_FAIL)

    def test_G3_assert_equal_is_red(self):
        self.assertVerdict("red", HEAD + "class T(unittest.TestCase):\n    def test_Q_add(self):\n        self.assertEqual([1], [])\n")

    def test_G3_bare_assert_is_red(self):
        self.assertVerdict("red", HEAD + "class T(unittest.TestCase):\n    def test_Q_add(self):\n        assert 1 == 2, 'not built'\n")

    def test_G3_assertion_in_a_helper_called_from_the_body_is_red(self):
        self.assertVerdict("red", HEAD + "def check(x):\n    assert x, 'missing'\n"
                           "class T(unittest.TestCase):\n    def test_Q_add(self):\n        check(False)\n")

    def test_G3_failing_subtest_is_red(self):
        self.assertVerdict("red", HEAD + "class T(unittest.TestCase):\n    def test_Q_add(self):\n"
                           "        for i in range(3):\n            with self.subTest(i=i):\n                self.assertLess(i, 2)\n")

    def test_G3_red_alongside_passing_and_skipped_tests(self):
        self.assertVerdict("red", HEAD + "class A(unittest.TestCase):\n    def test_ok(self):\n        pass\n"
                           "    @unittest.skip('x')\n    def test_skip(self):\n        pass\n"
                           "class B(unittest.TestCase):\n    def test_Q_add(self):\n        self.assertTrue(False)\n"
                           "    def test_ok2(self):\n        pass\n")

    # green
    def test_G3_all_passing_is_green(self):
        self.assertVerdict("green", HEAD + "class T(unittest.TestCase):\n    def test_a(self):\n        pass\n"
                           "    def test_b(self):\n        self.assertIn(1, [1])\n")

    def test_G3_skips_and_expected_failures_only_are_green(self):
        self.assertVerdict("green", HEAD + "class T(unittest.TestCase):\n    def test_a(self):\n        pass\n"
                           "    @unittest.skip('x')\n    def test_b(self):\n        self.fail('x')\n"
                           "    def test_c(self):\n        self.skipTest('later')\n"
                           "    @unittest.expectedFailure\n    def test_d(self):\n        self.assertEqual(1, 2)\n")
        self.assertVerdict("green", HEAD + "@unittest.skip('all')\nclass T(unittest.TestCase):\n    def test_a(self):\n        self.fail('x')\n")

    # unverified
    def test_G3_missing_module_at_the_top_is_unverified(self):
        self.assertVerdict("unverified", "import unittest\nimport app_not_built_q\nclass T(unittest.TestCase):\n"
                           "    def test_Q_add(self):\n        self.fail('x')\n")

    def test_G3_syntax_error_is_unverified(self):
        self.assertVerdict("unverified", HEAD + "class T(unittest.TestCase):\n    def test_Q_add(self):\n        self.fail('x'\n")

    def test_G3_name_error_in_body_is_unverified(self):
        self.assertVerdict("unverified", HEAD + "class T(unittest.TestCase):\n    def test_Q_add(self):\n        add(1)\n")

    def test_G3_zero_division_in_body_is_unverified(self):
        self.assertVerdict("unverified", HEAD + "class T(unittest.TestCase):\n    def test_Q_add(self):\n        1 / 0\n")

    def test_G3_import_of_missing_module_inside_body_is_unverified(self):
        self.assertVerdict("unverified", HEAD + "class T(unittest.TestCase):\n    def test_Q_add(self):\n        import app_not_built_q\n")

    def test_G3_error_inside_a_subtest_is_unverified(self):
        self.assertVerdict("unverified", HEAD + "class T(unittest.TestCase):\n    def test_Q_add(self):\n"
                           "        with self.subTest(i=1):\n            {}['k']\n")

    def test_G3_setup_raising_is_unverified(self):
        self.assertVerdict("unverified", HEAD + "class T(unittest.TestCase):\n    def setUp(self):\n        raise RuntimeError('x')\n"
                           "    def test_Q_add(self):\n        self.fail('x')\n")

    def test_G3_setup_failing_an_assertion_is_unverified(self):
        self.assertVerdict("unverified", HEAD + "class T(unittest.TestCase):\n    def setUp(self):\n        self.assertTrue(False)\n"
                           "    def test_Q_add(self):\n        self.fail('x')\n")

    def test_G3_teardown_raising_is_unverified(self):
        self.assertVerdict("unverified", HEAD + "class T(unittest.TestCase):\n    def tearDown(self):\n        raise OSError('x')\n"
                           "    def test_Q_add(self):\n        self.fail('x')\n")

    def test_G3_teardown_failing_an_assertion_is_unverified(self):
        self.assertVerdict("unverified", HEAD + "class T(unittest.TestCase):\n    def tearDown(self):\n        self.fail('teardown')\n"
                           "    def test_Q_add(self):\n        pass\n")
        self.assertVerdict("unverified", HEAD + "class T(unittest.TestCase):\n    def tearDown(self):\n        assert False\n"
                           "    def test_Q_add(self):\n        self.fail('x')\n")

    def test_G3_cleanup_failing_an_assertion_is_unverified(self):
        self.assertVerdict("unverified", HEAD + "class T(unittest.TestCase):\n    def test_Q_add(self):\n"
                           "        self.addCleanup(self.fail, 'cleanup')\n")

    def test_G3_setupclass_raising_is_unverified(self):
        self.assertVerdict("unverified", HEAD + "class T(unittest.TestCase):\n    @classmethod\n    def setUpClass(cls):\n"
                           "        raise RuntimeError('x')\n    def test_Q_add(self):\n        self.fail('x')\n"
                           "class U(unittest.TestCase):\n    def test_Q_more(self):\n        self.fail('x')\n")

    def test_G3_setupmodule_raising_is_unverified(self):
        self.assertVerdict("unverified", HEAD + "def setUpModule():\n    raise RuntimeError('x')\n"
                           "class T(unittest.TestCase):\n    def test_Q_add(self):\n        self.fail('x')\n")

    def test_G3_teardown_class_or_module_raising_is_unverified(self):
        self.assertVerdict("unverified", HEAD + "class T(unittest.TestCase):\n    @classmethod\n    def tearDownClass(cls):\n"
                           "        raise RuntimeError('x')\n    def test_Q_add(self):\n        self.fail('x')\n")
        self.assertVerdict("unverified", HEAD + "def tearDownModule():\n    raise RuntimeError('x')\n"
                           "class T(unittest.TestCase):\n    def test_Q_add(self):\n        self.fail('x')\n")

    def test_G3_sys_exit_in_a_test_is_unverified(self):
        for code in ("", "0", "1", "'bye'"):
            self.assertVerdict("unverified", "import sys, unittest\nclass T(unittest.TestCase):\n    def test_a(self):\n"
                               "        self.fail('x')\n    def test_b(self):\n        sys.exit(%s)\n" % code)

    def test_G3_os_exit_in_a_test_is_unverified(self):
        for code in ("0", "1", "5"):
            self.assertVerdict("unverified", "import os, unittest\nclass T(unittest.TestCase):\n    def test_a(self):\n"
                               "        self.fail('x')\n    def test_b(self):\n        os._exit(%s)\n" % code)

    def test_G3_functions_only_module_is_unverified(self):
        self.assertVerdict("unverified", "def test_Q_add():\n    assert 1 == 2\n")
        self.assertVerdict("unverified", HEAD)

    def test_G3_direct_script_is_unverified(self):
        self.assertVerdict("unverified", "x = 1 + 1\nassert x == 2\nprint('checked')\n")
        self.assertVerdict("unverified", "import sys\nprint('FAILED: add is missing')\nsys.exit(1)\n")

    def test_G3_one_assertion_failure_with_any_error_is_unverified(self):
        self.assertVerdict("unverified", HEAD + "class T(unittest.TestCase):\n    def test_Q_add(self):\n        self.fail('x')\n"
                           "    def test_Q_other(self):\n        raise KeyError('k')\n")
        self.assertVerdict("unverified", HEAD + "class T(unittest.TestCase):\n    def test_Q_add(self):\n        self.fail('x')\n"
                           "class U(unittest.TestCase):\n    def setUp(self):\n        open('/nonexistent/q')\n"
                           "    def test_Q_more(self):\n        pass\n")

    def test_G3_path_not_ending_in_py_is_unverified(self):
        self.assertVerdict("unverified", RED_FAIL, rel="tests/test_x")
        self.assertVerdict("unverified", "test('x', () => { throw new Error('x') })\n", rel="tests/test_x.test.js")


class G4Validate(Gate):

    ANS = {"status": "done", "summary": "", "non-claims": [], "tests": ["tests/test_x.py"],
           "covers": [{"section": "Q-add", "tests": ["test_Q_add"]}]}

    def run_validate(self, d, before, ans=None, request=None):
        teujip = worker.load_member("teujip")
        return worker.validate(json.loads(json.dumps(ans or self.ANS)), teujip, request or dict(REQUEST), d, "", "claude-code", before)

    def failed_with(self, out, text):
        self.assertEqual(out["status"], "failed", out)
        self.assertIn("red-before-build", out.get("validation", {}).get("failed", []), out)
        self.assertTrue(any(text in n for n in out["non-claims"]), out)

    def unverified_message(self, out, path):
        prefix = "red-before-build: %s is not verified red — " % path
        hits = [n for n in out["non-claims"] if n.startswith(prefix)]
        self.assertTrue(hits, out)
        self.assertTrue(hits[0][len(prefix):].strip(), "the detail follows the dash: %r" % hits[0])

    def test_G4_red_passes(self):
        d = self.repo()
        before = worker.tree_state(d)
        self.write(d, "tests/test_x.py", RED_FAIL)
        self.fn("unittest_red")
        out = self.run_validate(d, before)
        self.assertEqual(out["status"], "done", out)

    def test_G4_import_error_is_not_verified_red(self):
        d = self.repo()
        before = worker.tree_state(d)
        self.write(d, "tests/test_x.py", HEAD + "class T(unittest.TestCase):\n    def test_Q_add(self):\n        import app\n")
        out = self.run_validate(d, before)
        self.failed_with(out, "red-before-build: tests/test_x.py is not verified red — ")
        self.unverified_message(out, "tests/test_x.py")

    def test_G4_no_tests_is_not_verified_red(self):
        d = self.repo()
        before = worker.tree_state(d)
        self.write(d, "tests/test_x.py", HEAD)
        out = self.run_validate(d, before)
        self.failed_with(out, "red-before-build: tests/test_x.py is not verified red — ")
        self.unverified_message(out, "tests/test_x.py")

    def test_G4_unverified_whatever_built_before_says(self):
        d = self.repo()
        self.write(d, "app.py", "x = 1\n")   # an earlier build attempt, uncommitted
        before = worker.tree_state(d)
        self.write(d, "tests/test_x.py", "import unittest\nimport app_missing_q\nclass T(unittest.TestCase):\n"
                   "    def test_Q_add(self):\n        self.fail('x')\n")
        out = self.run_validate(d, before)
        self.failed_with(out, "red-before-build: tests/test_x.py is not verified red — ")
        self.unverified_message(out, "tests/test_x.py")
        self.assertFalse(any("could not decide" in n for n in out["non-claims"]), out)

    def test_G4_green_is_the_existing_problem(self):
        d = self.repo()
        before = worker.tree_state(d)
        self.write(d, "tests/test_x.py", HEAD + "class T(unittest.TestCase):\n    def test_Q_add(self):\n        pass\n"
                   "    @unittest.expectedFailure\n    def test_Q_more(self):\n        self.fail('x')\n")
        self.fn("unittest_red")
        out = self.run_validate(d, before)
        self.failed_with(out, "red-before-build: tests/test_x.py passes before the build — it decides nothing")
        self.assertFalse(any("not verified red" in n for n in out["non-claims"]), out)

    def test_G4_unexpected_success_is_green_not_red(self):
        d = self.repo()
        before = worker.tree_state(d)
        self.write(d, "tests/test_x.py", HEAD + "class T(unittest.TestCase):\n"
                   "    @unittest.expectedFailure\n    def test_Q_add(self):\n        pass\n")
        out = self.run_validate(d, before)
        self.failed_with(out, "red-before-build: tests/test_x.py passes before the build — it decides nothing")

    def test_G4_green_with_code_built_before_is_the_existing_non_claim(self):
        d = self.repo()
        self.write(d, "app.py", "x = 1\n")
        before = worker.tree_state(d)
        self.write(d, "tests/test_x.py", GREEN)
        self.fn("unittest_red")
        out = self.run_validate(d, before)
        self.assertEqual(out["status"], "done", out)
        self.assertTrue(any(n.startswith("red-before-build could not decide tests/test_x.py: it passes, and code was already changed before this call (")
                            and "app.py" in n for n in out["non-claims"]), out)

    def test_G4_each_file_judged_one_unverified_fails_the_answer(self):
        d = self.repo()
        before = worker.tree_state(d)
        self.write(d, "tests/test_x.py", RED_FAIL)
        self.write(d, "tests/test_y.py", HEAD + "class T(unittest.TestCase):\n    def test_Q_add(self):\n        self.fail('x')\n"
                   "    def test_Q_b(self):\n        1 / 0\n")
        ans = dict(json.loads(json.dumps(self.ANS)), tests=["tests/test_x.py", "tests/test_y.py"])
        out = self.run_validate(d, before, ans)
        self.failed_with(out, "red-before-build: tests/test_y.py is not verified red — ")
        self.assertFalse(any(n.startswith("red-before-build: tests/test_x.py") for n in out["non-claims"]), out)


class G5Preserved(Gate):

    ANS = G4Validate.ANS

    def test_G5_amending_skips_the_gate(self):
        d = self.repo()
        before = worker.tree_state(d)
        self.write(d, "tests/test_x.py", "import unittest\nimport app_missing_q\n")
        amend = dict(REQUEST, amending=[{"test": "tests/test_x.py", "contract_quote": "x", "why": "y"}])
        out = worker.validate(json.loads(json.dumps(self.ANS)), worker.load_member("teujip"), amend, d, "", "claude-code", before)
        self.assertEqual(out["status"], "done", out)

    def test_G5_deleted_by_the_writer_is_said_and_skipped(self):
        d = self.repo()
        self.write(d, "tests/test_old.py", "import unittest\n")
        subprocess.run(["git", "add", "-A"], cwd=d, check=True)
        subprocess.run(["git", "commit", "-qm", "old"], cwd=d, check=True)
        before = worker.tree_state(d)
        os.remove(os.path.join(d, "tests", "test_old.py"))
        self.write(d, "tests/test_x.py", RED_FAIL)
        ans = dict(json.loads(json.dumps(self.ANS)), tests=["tests/test_x.py", "tests/test_old.py"])
        out = worker.validate(ans, worker.load_member("teujip"), dict(REQUEST), d, "", "claude-code", before)
        self.assertIn("deleted by the writer: tests/test_old.py — the contract retires it", out["non-claims"], out)
        self.assertEqual(out["status"], "done", out)

    def test_G5_deleted_tests_of_the_request_are_skipped(self):
        d = self.repo()
        before = worker.tree_state(d)
        self.write(d, "tests/test_x.py", RED_FAIL)
        ans = dict(json.loads(json.dumps(self.ANS)), tests=["tests/test_x.py", "tests/test_gone.py"])
        request = dict(REQUEST, tests=["tests/test_x.py"], **{"deleted-tests": ["tests/test_gone.py"]})
        out = worker.validate(ans, worker.load_member("teujip"), request, d, "", "claude-code", before)
        self.assertEqual(out["status"], "done", out)

    def test_G5_a_test_that_never_existed_is_the_problem(self):
        d = self.repo()
        before = worker.tree_state(d)
        self.write(d, "tests/test_x.py", RED_FAIL)
        ans = dict(json.loads(json.dumps(self.ANS)), tests=["tests/test_x.py", "tests/test_nowhere.py"])
        out = worker.validate(ans, worker.load_member("teujip"), dict(REQUEST), d, "", "claude-code", before)
        self.assertEqual(out["status"], "failed", out)
        self.assertIn("red-before-build: tests/test_nowhere.py does not exist", out["non-claims"], out)


class G7NothingElse(Gate):

    def test_G7_validators_and_validate_signature_unchanged(self):
        self.assertEqual(worker.VALIDATORS, ("quotes-required", "no-tree-changes", "checks-ran", "red-before-build", "readme-only",
                                             "only-tests-touched", "tests-kept", "explanation-kept"))
        self.assertEqual(list(inspect.signature(worker.validate).parameters),
                         ["out", "member", "request", "target", "stream_text", "host", "before", "protected_before"])

    def test_G7_only_tests_touched_still_fires(self):
        d = self.repo()
        before = worker.tree_state(d)
        self.write(d, "tests/test_x.py", RED_FAIL)
        self.write(d, "app.py", "stub = 1\n")
        out = worker.validate(json.loads(json.dumps(G4Validate.ANS)), worker.load_member("teujip"), dict(REQUEST), d, "", "claude-code", before)
        self.assertEqual(out["status"], "failed", out)
        self.assertIn("changed outside the tests it declared: app.py", " ".join(out["non-claims"]), out)

    def test_G7_previous_slices_tests_unchanged_and_passing(self):
        for f in ("test_record_paths.py", "test_native_prompt.py", "test_hostcall_env.py"):
            diff = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", f], cwd=HERE)
            self.assertEqual(diff.returncode, 0, "%s changed" % f)
            done = subprocess.run([sys.executable, "-m", "unittest", f], cwd=HERE, capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, "%s\n%s" % (f, done.stderr[-3000:]))


class G8NoTimeout(Gate):

    def test_G8_hostcall_untouched(self):
        diff = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", "hostcall.py"], cwd=HERE)
        self.assertEqual(diff.returncode, 0, "hostcall.py changed")

    def test_G8_unittest_red_takes_no_option(self):
        ur = self.fn("unittest_red")
        self.assertEqual(list(inspect.signature(ur).parameters), ["target", "path"])

    def test_G8_no_timeout_passed_to_the_process(self):
        ur = self.fn("unittest_red")
        seen = []
        real_run, real_comm, real_wait = subprocess.run, subprocess.Popen.communicate, subprocess.Popen.wait

        def run(*a, **k):
            seen.append(("run", k.get("timeout")))
            return real_run(*a, **k)

        def comm(self_, *a, **k):
            seen.append(("communicate", k.get("timeout", a[1] if len(a) > 1 else None)))
            return real_comm(self_, *a, **k)

        def wait(self_, *a, **k):
            seen.append(("wait", k.get("timeout", a[0] if a else None)))
            return real_wait(self_, *a, **k)

        d = self.tmp()
        self.write(d, "tests/test_x.py", RED_FAIL)
        with mock.patch.object(subprocess, "run", run), mock.patch.object(subprocess.Popen, "communicate", comm), \
                mock.patch.object(subprocess.Popen, "wait", wait):
            self.assertEqual(self.shape(ur(d, "tests/test_x.py"))[0], "red")
        self.assertTrue(seen, "no process was observed")
        self.assertEqual([s for s in seen if s[1] is not None], [], seen)



class G9NoPassFds(Gate):
    """subprocess.Popen replaced by one that refuses a non-empty pass_fds as CPython does on Windows."""

    def windows_popen(self, seen, refuse=True):
        real = subprocess.Popen

        class WindowsPopen(real):
            def __init__(self_, *a, **k):
                seen.append(tuple(k.get("pass_fds") or ()))
                if refuse and k.get("pass_fds"):
                    raise AssertionError("pass_fds not supported on Windows.")
                super().__init__(*a, **k)

        return mock.patch("subprocess.Popen", WindowsPopen)

    def call(self, d, rel, seen, refuse=True):
        ur = self.fn("unittest_red")
        try:
            with self.windows_popen(seen, refuse):
                got = ur(d, rel)
        except BaseException as e:  # noqa: B902 — a raise is the failure under test, not an error of the test
            self.fail("unittest_red raised %s: %s" % (type(e).__name__, e))
        self.assertTrue(seen, "the harness was not started through subprocess.Popen")
        return self.shape(got)

    def windows_verdict(self, want, text, rel="tests/test_x.py"):
        d = self.tmp()
        self.write(d, rel, text)
        seen = []
        got = self.call(d, rel, seen)
        self.assertEqual(got[0], want, "%s\n--- fixture ---\n%s" % (got, text))
        return got

    def test_G9_self_fail_is_red_without_pass_fds(self):
        self.windows_verdict("red", RED_FAIL)

    def test_G9_all_passing_is_green_without_pass_fds(self):
        self.windows_verdict("green", GREEN)

    def test_G9_missing_module_at_the_top_is_unverified_without_pass_fds(self):
        self.windows_verdict("unverified", "import unittest\nimport app_not_built_q\nclass T(unittest.TestCase):\n"
                             "    def test_Q_add(self):\n        self.fail('x')\n")

    def test_G9_os_exit_zero_is_unverified_without_pass_fds(self):
        fake = json.dumps(report(tests_run=1))
        self.windows_verdict("unverified", "import os, unittest\nclass T(unittest.TestCase):\n    def test_Q_add(self):\n"
                             "        print(%r); os._exit(0)\n" % fake)

    def test_G9_no_file_descriptor_is_passed_even_where_allowed(self):
        d = self.tmp()
        self.write(d, "tests/test_x.py", RED_FAIL)
        seen = []
        self.assertEqual(self.call(d, "tests/test_x.py", seen, refuse=False)[0], "red")
        self.assertEqual([fds for fds in seen if fds], [], "pass_fds given to the harness: %r" % seen)

    def test_G9_printed_output_is_still_not_the_verdict(self):
        fake = json.dumps(report(tests_run=1, assertion_failures=1))
        self.windows_verdict("green", "import sys, os, unittest\nclass T(unittest.TestCase):\n    def test_Q_add(self):\n"
                             "        msg = 'FAIL: test_Q_add\\nAssertionError\\nFAILED (failures=1)\\n' + %r + '\\n'\n"
                             "        print(msg); sys.stderr.write(msg); os.write(1, msg.encode()); os.write(2, msg.encode())\n" % fake)
        ok = json.dumps(report(tests_run=1))
        self.windows_verdict("red", "import sys, os, unittest\nclass T(unittest.TestCase):\n    def test_Q_add(self):\n"
                             "        msg = '\\nRan 1 test in 0.000s\\n\\nOK\\n' + %r + '\\n'\n"
                             "        print(msg); sys.stderr.write(msg); os.write(1, msg.encode()); os.write(2, msg.encode())\n"
                             "        self.fail('not built')\n" % ok)

    def test_G9_leaves_nothing_in_the_target_but_pycache_and_removes_its_scratch(self):
        d = self.repo()
        cases = {"tests/test_red.py": RED_FAIL, "tests/test_green.py": GREEN,
                 "tests/test_err.py": "import nowhere_q\n" + RED_FAIL, "test_root.py": RED_FAIL,
                 "tests/test_exit.py": "import os, unittest\nclass T(unittest.TestCase):\n    def test_Q_add(self):\n        os._exit(0)\n"}
        want = {"tests/test_red.py": "red", "tests/test_green.py": "green", "tests/test_err.py": "unverified", "test_root.py": "red",
                "tests/test_exit.py": "unverified"}
        for rel, text in cases.items():
            self.write(d, rel, text)
        subprocess.run(["git", "add", "-A"], cwd=d, check=True)
        subprocess.run(["git", "commit", "-qm", "fixtures"], cwd=d, check=True)
        listing = lambda: sorted(os.path.relpath(os.path.join(a, f), d) for a, _, fs in os.walk(d) if ".git" not in a.split(os.sep)
                                 and "__pycache__" not in a.split(os.sep) for f in fs)
        before = listing()
        scratch = self.tmp()   # where a scratch file made through tempfile would go; it must be gone afterwards
        with mock.patch.object(tempfile, "tempdir", scratch), mock.patch.dict(os.environ, {"TMPDIR": scratch, "TEMP": scratch, "TMP": scratch}):
            for rel in cases:
                seen = []
                self.assertEqual(self.call(d, rel, seen)[0], want[rel], rel)
        st = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all", "--ignored"], cwd=d, capture_output=True, text=True).stdout
        self.assertEqual([l for l in st.splitlines() if "__pycache__" not in l], [], st)
        self.assertEqual(listing(), before)
        self.assertEqual(os.listdir(scratch), [], "scratch left behind")

if __name__ == "__main__":
    unittest.main()
