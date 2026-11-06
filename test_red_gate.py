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

ROOT = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.join(ROOT, "plugin")
sys.path.insert(0, PLUGIN)
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

    def test_G3_F9_functions_only_module_failing_an_assertion_is_red_and_no_tests_is_unverified(self):
        self.assertVerdict("red", "def test_Q_add():\n    assert 1 == 2\n")
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
        # The 2.0.x HEAD guard is retired: the package split changes these suites' bootstrap paths.
        for f in ("test_record_paths.py", "test_native_prompt.py", "test_hostcall_env.py"):
            done = subprocess.run([sys.executable, "-m", "unittest", f], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, "%s\n%s" % (f, done.stderr[-3000:]))


class G8NoTimeout(Gate):

    def test_G8_hostcall_passes_no_timeout(self):
        import hostcall
        d = self.tmp()
        calls = []

        def run(cmd, *a, **k):
            calls.append(k)
            return subprocess.CompletedProcess(cmd, 0, b"", b"")

        with mock.patch.dict(os.environ, {"PATH": os.environ.get("PATH", ""), "HOME": d}, clear=True), \
                mock.patch.object(subprocess, "run", run):
            hostcall.run_claude("p", {"type": "object"}, cwd=d)
            hostcall.run_codex("p", {"type": "object"}, d, beside=os.path.join(d, "r.json"))
        self.assertEqual(len(calls), 2, calls)
        self.assertEqual([k for k in calls if "timeout" in k], [], calls)

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


BROAD = HEAD + "class T(unittest.TestCase):\n    failureException = Exception\n"


class G10OnlyAssertionErrors(Gate):
    """Real unittest files whose failureException is broader than AssertionError: only AssertionError failures prove red."""

    def test_G10_broad_failure_exception_with_a_runtime_error_body_is_unverified(self):
        self.assertVerdict("unverified", BROAD + "    def test_Q_add(self):\n        raise RuntimeError('runtime failure, not assertion')\n")

    def test_G10_broad_failure_exception_with_a_runtime_error_in_a_subtest_is_unverified(self):
        self.assertVerdict("unverified", BROAD + "    def test_Q_add(self):\n        with self.subTest(i=1):\n"
                           "            raise RuntimeError('runtime failure, not assertion')\n")

    def test_G10_broad_failure_exception_with_self_fail_is_unverified(self):
        # self.fail raises self.failureException, here a plain Exception
        self.assertVerdict("unverified", BROAD + "    def test_Q_add(self):\n        self.fail('not built')\n")

    def test_G10_broad_failure_exception_with_assert_equal_is_unverified(self):
        self.assertVerdict("unverified", BROAD + "    def test_Q_add(self):\n        self.assertEqual(1, 2)\n")

    def test_G10_broad_failure_exception_with_other_error_types_is_unverified(self):
        for exc in ("ValueError('v')", "KeyError('k')", "OSError('o')", "type('Custom', (Exception,), {})('c')"):
            with self.subTest(exc=exc):
                self.assertVerdict("unverified", BROAD + "    def test_Q_add(self):\n        raise %s\n" % exc)

    def test_G10_base_exception_failure_exception_is_unverified(self):
        self.assertVerdict("unverified", HEAD + "class T(unittest.TestCase):\n    failureException = BaseException\n"
                           "    def test_Q_add(self):\n        raise RuntimeError('runtime failure, not assertion')\n")

    def test_G10_runtime_error_as_failure_exception_is_unverified(self):
        self.assertVerdict("unverified", HEAD + "class T(unittest.TestCase):\n    failureException = RuntimeError\n"
                           "    def test_Q_add(self):\n        self.fail('not built')\n")

    def test_G10_one_genuine_assertion_plus_one_non_assertion_failure_is_unverified(self):
        self.assertVerdict("unverified", HEAD + "class A(unittest.TestCase):\n    def test_Q_add(self):\n        self.fail('not built')\n"
                           "class B(unittest.TestCase):\n    failureException = Exception\n"
                           "    def test_Q_add_too(self):\n        raise RuntimeError('runtime failure, not assertion')\n")
        self.assertVerdict("unverified", BROAD + "    def test_Q_add(self):\n        assert 1 == 2, 'not built'\n"
                           "    def test_Q_add_too(self):\n        raise RuntimeError('runtime failure, not assertion')\n")

    def test_G10_genuine_and_non_assertion_failures_in_subtests_of_one_test_is_unverified(self):
        self.assertVerdict("unverified", BROAD + "    def test_Q_add(self):\n"
                           "        with self.subTest(i=0):\n            assert False, 'not built'\n"
                           "        with self.subTest(i=1):\n            raise RuntimeError('runtime failure, not assertion')\n")

    def test_G10_genuine_assertion_errors_in_the_body_are_still_red(self):
        for body in ("self.fail('not built')", "self.assertEqual(1, 2)", "assert 1 == 2, 'not built'"):
            with self.subTest(body=body):
                self.assertVerdict("red", HEAD + "class T(unittest.TestCase):\n    def test_Q_add(self):\n        %s\n" % body)

    def test_G10_assertion_error_subclass_as_failure_exception_is_still_red(self):
        sub = HEAD + "class Missing(AssertionError):\n    pass\nclass T(unittest.TestCase):\n    failureException = Missing\n"
        for body in ("self.fail('not built')", "self.assertEqual(1, 2)", "raise Missing('not built')"):
            with self.subTest(body=body):
                self.assertVerdict("red", sub + "    def test_Q_add(self):\n        %s\n" % body)
        self.assertVerdict("red", sub + "    def test_Q_add(self):\n        with self.subTest(i=1):\n            self.fail('not built')\n")

    def test_G10_bare_assert_under_a_broad_failure_exception_is_still_red(self):
        self.assertVerdict("red", BROAD + "    def test_Q_add(self):\n        assert 1 == 2, 'not built'\n")
        self.assertVerdict("red", BROAD + "    def test_Q_add(self):\n        raise AssertionError('not built')\n")

    def test_G10_bare_assert_in_a_subtest_under_a_broad_failure_exception_is_still_red(self):
        self.assertVerdict("red", BROAD + "    def test_Q_add(self):\n        with self.subTest(i=1):\n            assert False, 'not built'\n")

    def test_G10_assertion_failures_in_setup_or_teardown_are_still_unverified(self):
        for hook in ("setUp", "tearDown"):
            for head in (HEAD + "class T(unittest.TestCase):\n", BROAD):
                with self.subTest(hook=hook, broad=head == BROAD):
                    self.assertVerdict("unverified", head + "    def %s(self):\n        assert False, 'fixture'\n"
                                       "    def test_Q_add(self):\n        assert False, 'not built'\n" % hook)

    def test_G10_non_assertion_failures_in_setup_under_a_broad_failure_exception_are_unverified(self):
        self.assertVerdict("unverified", BROAD + "    def setUp(self):\n        raise RuntimeError('fixture')\n"
                           "    def test_Q_add(self):\n        assert False, 'not built'\n")

    def test_G10_a_passing_file_with_a_broad_failure_exception_is_still_green(self):
        self.assertVerdict("green", BROAD + "    def test_Q_add(self):\n        self.assertEqual(1, 1)\n")



# Contract HC1: module-level test_* functions the file itself defines, callable with no arguments, are collected as unittest tests.
FN_RED = "def test_Q_add():\n    assert 1 == 2, 'not built'\n"
FN_GREEN = "def test_Q_ok():\n    assert 1 == 1\n"
NO_TESTS_RAN = "no tests ran"


class G11Functions(Gate):
    """unittest_red on function-style fixture files in temporary directories."""

    def marker(self):
        return os.path.join(self.tmp(), "ran")

    def marking(self, path, name="test_Q_mark"):
        return "def %s():\n    open(%r, 'w').write('x')\n" % (name, path)

    def assertErrorVerdict(self, text, rel="tests/test_x.py", files=None):
        verdict, detail = self.assertVerdict("unverified", text, rel, files)
        self.assertNotIn(NO_TESTS_RAN, detail, "the functions were not run: %s\n--- fixture ---\n%s" % (detail, text))
        return verdict, detail

    # F2 red
    def test_F2_bare_assert_in_a_function_is_red(self):
        self.assertVerdict("red", FN_RED)

    def test_F2_raise_assertion_error_in_a_function_is_red(self):
        self.assertVerdict("red", "def test_Q_add():\n    raise AssertionError('not built')\n")

    def test_F2_assertion_error_subclass_in_a_function_is_red(self):
        self.assertVerdict("red", "class Mismatch(AssertionError):\n    pass\n\ndef test_Q_add():\n    raise Mismatch('not built')\n")

    def test_F2_assertion_in_a_same_file_helper_the_function_calls_is_red(self):
        self.assertVerdict("red", "def check(x):\n    assert x, 'missing'\n\ndef test_Q_add():\n    check(False)\n")

    def test_F2_red_beside_passing_functions_is_red(self):
        self.assertVerdict("red", FN_GREEN + FN_RED + "def test_Q_more():\n    pass\n")

    def test_F2_function_with_only_defaulted_and_star_parameters_is_collected(self):
        self.assertVerdict("red", "def test_Q_add(x=1, *args, **kwargs):\n    assert x == 2\n")
        self.assertVerdict("red", "def test_Q_add(*args, **kwargs):\n    assert args == (1,)\n")
        self.assertVerdict("red", "def test_Q_add(*, flag=False):\n    assert flag\n")

    # F4 green
    def test_F4_all_passing_functions_are_green(self):
        self.assertVerdict("green", FN_GREEN + "def test_Q_more():\n    assert [1] == [1]\n")

    def test_F4_a_function_printing_failed_and_returning_is_green(self):
        fake = json.dumps(report(tests_run=1, assertion_failures=1))
        self.assertVerdict("green", "import os, sys\n\ndef test_Q_add():\n"
                           "    msg = 'FAIL: test_Q_add\\nAssertionError\\nFAILED (failures=1)\\n' + %r + '\\n'\n"
                           "    print(msg); sys.stderr.write(msg); os.write(1, msg.encode()); os.write(2, msg.encode())\n" % fake)

    def test_F4_the_files_own_main_runner_exiting_1_is_not_the_verdict(self):
        self.assertVerdict("green", "import sys\n\n" + FN_GREEN +
                           "\nif __name__ == '__main__':\n    print('FAILED (failures=1)')\n    sys.exit(1)\n")

    def test_F4_the_files_own_main_runner_exiting_0_does_not_hide_red(self):
        self.assertVerdict("red", "import sys\n\n" + FN_RED +
                           "\nif __name__ == '__main__':\n    print('OK')\n    sys.exit(0)\n")

    # F3 error
    def test_F3_name_error_beside_a_red_function_is_unverified(self):
        self.assertErrorVerdict(FN_RED + "def test_Q_other():\n    add(1)\n")

    def test_F3_import_of_a_missing_module_inside_the_body_is_unverified(self):
        self.assertErrorVerdict(FN_RED + "def test_Q_other():\n    import app_not_built_q\n")

    def test_F3_runtime_error_beside_a_red_function_is_unverified(self):
        self.assertErrorVerdict(FN_RED + "def test_Q_other():\n    raise RuntimeError('x')\n")

    def test_F3_other_exceptions_beside_a_red_function_are_unverified(self):
        for body in ("1 / 0", "{}['k']", "None.missing", "raise ValueError('v')"):
            with self.subTest(body=body):
                self.assertErrorVerdict(FN_RED + "def test_Q_other():\n    %s\n" % body)

    def test_F3_a_suites_own_skip_exception_is_an_error(self):
        self.assertErrorVerdict("class Skip(Exception):\n    pass\n\n" + FN_RED + "def test_Q_later():\n    raise Skip('later')\n")

    def test_F3_sys_exit_in_a_function_is_unverified(self):
        for code in ("", "0", "1", "'bye'"):
            with self.subTest(code=code):
                self.assertErrorVerdict("import sys\n\n" + FN_RED + "def test_Q_exit():\n    sys.exit(%s)\n" % code)

    def test_F3_an_erroring_function_beside_a_testcase_assertion_failure_is_unverified(self):
        self.assertVerdict("unverified", RED_FAIL + "\ndef test_Q_other():\n    raise RuntimeError('x')\n")

    def test_F3_os_exit_in_a_function_leaves_no_report(self):
        for code in ("0", "1"):
            with self.subTest(code=code):
                self.assertErrorVerdict("import os\n\n" + FN_RED + "def test_Q_exit():\n    os._exit(%s)\n" % code)

    # F6 mixed
    def test_F6_testcase_failure_with_passing_functions_is_red_and_both_run(self):
        m = self.marker()
        self.assertVerdict("red", RED_FAIL + "\n" + self.marking(m))
        self.assertTrue(os.path.exists(m), "the function did not run")

    def test_F6_passing_testcases_with_a_function_assertion_failure_is_red(self):
        self.assertVerdict("red", GREEN + "\n" + FN_RED)

    def test_F6_testcase_error_with_passing_functions_is_unverified_and_both_run(self):
        m = self.marker()
        self.assertVerdict("unverified", HEAD + "class T(unittest.TestCase):\n    def test_Q_add(self):\n        1 / 0\n\n" + self.marking(m))
        self.assertTrue(os.path.exists(m), "the function did not run")

    def test_F6_passing_testcases_with_an_erroring_function_is_unverified(self):
        self.assertVerdict("unverified", GREEN + "\ndef test_Q_other():\n    raise KeyError('k')\n")

    def test_F6_function_failure_with_a_testcase_error_is_unverified_and_both_run(self):
        m = self.marker()
        self.assertVerdict("unverified", HEAD + "class T(unittest.TestCase):\n    def test_Q_add(self):\n        raise OSError('x')\n\n"
                           "def test_Q_fn():\n    open(%r, 'w').write('x')\n    assert False\n" % m)
        self.assertTrue(os.path.exists(m), "the function did not run")

    def test_F6_all_passing_is_green_and_both_run(self):
        m = self.marker()
        self.assertVerdict("green", GREEN + "\n" + self.marking(m))
        self.assertTrue(os.path.exists(m), "the function did not run")

    def test_F6_setupmodule_raising_makes_a_function_only_file_unverified(self):
        self.assertErrorVerdict("def setUpModule():\n    raise RuntimeError('x')\n\n" + FN_RED)

    def test_F6_setupmodule_runs_before_functions(self):
        self.assertVerdict("red", "STATE = {}\n\ndef setUpModule():\n    STATE['k'] = 1\n\n"
                           "def test_Q_uses():\n    STATE['k']\n\n" + FN_RED)

    # F1 / F7 what is collected
    HELPER = ("def test_x():\n    assert False, 'imported red'\n\n"
              "def test_z():\n    raise RuntimeError('imported error')\n\n"
              "def test_w():\n    assert False, 'imported by assignment'\n")

    def test_F1_imported_red_or_erroring_functions_are_not_collected(self):
        files = {"helper_fx.py": self.HELPER}
        self.assertVerdict("green", "from helper_fx import test_x\n\n" + FN_GREEN, files=files)
        self.assertVerdict("green", "import helper_fx\ntest_y = helper_fx.test_z\n\n" + FN_GREEN, files=files)
        self.assertVerdict("green", "from helper_fx import test_x, test_z\nimport helper_fx\ntest_v = helper_fx.test_w\n\n" + FN_GREEN,
                           files=files)

    def test_F1_imported_functions_do_not_hide_an_own_red_function(self):
        self.assertVerdict("red", "from helper_fx import test_x\n\n" + FN_RED, files={"helper_fx.py": self.HELPER})

    def test_F7_a_file_whose_only_test_function_is_imported_has_no_tests(self):
        verdict, detail = self.assertVerdict("unverified", "from helper_fx import test_x\nimport helper_fx\ntest_y = helper_fx.test_z\n",
                                             rel="checks/probe.py", files={"helper_fx.py": self.HELPER})
        for word in ("unittest", "TestCase", "test_"):
            self.assertIn(word, detail)

    def test_F1_a_function_needing_arguments_is_not_collected(self):
        self.assertVerdict("red", FN_RED + "def test_needs(tmp_path):\n    raise RuntimeError(tmp_path)\n")
        self.assertVerdict("red", FN_RED + "def test_kw(a, *, b):\n    raise RuntimeError(a)\n")
        self.assertVerdict("red", FN_RED + "def test_kwonly(*, b):\n    raise RuntimeError(b)\n")

    def test_F1_a_file_with_only_argument_needing_functions_has_no_tests(self):
        verdict, detail = self.assertVerdict("unverified", "def test_needs(tmp_path):\n    assert False\n\n"
                                             "def test_kw(a, *, b):\n    assert False\n", rel="checks/probe.py")
        self.assertIn("test_", detail)

    def test_F1_a_class_or_callable_object_named_test_is_not_collected(self):
        self.assertVerdict("green", "class test_thing:\n    def __init__(self):\n        raise AssertionError('class')\n\n" + FN_GREEN)
        self.assertVerdict("green", "class Boom:\n    def __call__(self):\n        raise AssertionError('callable')\n\n"
                           "test_obj = Boom()\n\n" + FN_GREEN)
        self.assertVerdict("green", "import functools\n\ndef boom():\n    raise RuntimeError('partial')\n\n"
                           "test_partial = functools.partial(boom)\n\n" + FN_GREEN)

    def test_F1_nested_functions_are_not_collected(self):
        self.assertVerdict("green", "class Holder:\n    @staticmethod\n    def test_static():\n        raise AssertionError('in a class')\n\n"
                           "def outer():\n    def test_inner():\n        raise AssertionError('nested')\n    return test_inner\n\n" + FN_GREEN)

    def test_F1_functions_not_named_test_underscore_are_not_collected(self):
        self.assertVerdict("green", "def check_q():\n    raise AssertionError('x')\n\n"
                           "def testq():\n    raise AssertionError('x')\n\n"
                           "def Test_q():\n    raise RuntimeError('x')\n\n"
                           "def tests_q():\n    raise AssertionError('x')\n\n" + FN_GREEN)

    def test_F1_load_tests_decides_and_no_function_is_added(self):
        m = self.marker()
        body = (self.marking(m, "test_Q_fn") + FN_RED)
        self.assertVerdict("red", body)   # without load_tests the functions are collected
        m2 = self.marker()
        self.assertVerdict("green", HEAD + "class T(unittest.TestCase):\n    def test_Q_ok(self):\n        pass\n\n"
                           "def load_tests(loader, tests, pattern):\n    return unittest.TestSuite([T('test_Q_ok')])\n\n"
                           + self.marking(m2, "test_Q_fn") + FN_RED)
        self.assertFalse(os.path.exists(m2), "a function was added to what load_tests returned")

    # F5 skip and expected failure
    def test_F5_skiptest_raised_in_a_function_is_skipped(self):
        self.assertVerdict("green", "import unittest\n\ndef test_Q_add():\n    raise unittest.SkipTest('later')\n\n" + FN_GREEN)

    def test_F5_skip_decorators_on_functions_skip(self):
        self.assertVerdict("green", HEAD + "\n@unittest.skip('later')\ndef test_Q_add():\n    assert False\n\n" + FN_GREEN)
        self.assertVerdict("green", HEAD + "\n@unittest.skipIf(True, 'later')\ndef test_Q_add():\n    raise RuntimeError('x')\n\n" + FN_GREEN)

    def test_F5_skipif_false_runs_the_function(self):
        self.assertVerdict("red", HEAD + "\n@unittest.skipIf(False, 'runs')\ndef test_Q_add():\n    assert False\n")

    def test_F5_expected_failure_on_a_function_is_not_red(self):
        self.assertVerdict("green", HEAD + "\n@unittest.expectedFailure\ndef test_Q_add():\n    assert False\n")
        self.assertVerdict("green", HEAD + "\n@unittest.expectedFailure\ndef test_Q_add():\n    pass\n\n" + FN_GREEN)

    # F7 no tests
    def test_F7_no_tests_detail_names_unittest_testcase_and_test_(self):
        for r in (report(), report(skipped=1), report(assertion_failures=1)):
            verdict, detail = self.shape(self.fn("red_verdict")(r))
            self.assertEqual(verdict, "unverified", r)
            for word in ("unittest", "TestCase", "test_"):
                self.assertIn(word, detail, r)

    def test_F7_a_file_with_no_testcase_and_no_function_is_unverified(self):
        verdict, detail = self.assertVerdict("unverified", "import unittest\nVALUE = 1\n\ndef helper():\n    assert False\n",
                                             rel="checks/probe.py")
        self.assertIn("test_", detail)


    # F10 a collected function whose call returns a coroutine, generator or async generator never ran its body
    ASYNC_ONLY = "async def test_Q_add():\n    assert 1 == 2, 'not built'\n"

    def assertNeverRan(self, text, marker=None):
        verdict, detail = self.assertVerdict("unverified", text)
        self.assertNotIn(NO_TESTS_RAN, detail, "the functions were not collected: %s\n--- fixture ---\n%s" % (detail, text))
        self.assertIn("never ran", detail, "the detail does not say the body never ran: %s\n--- fixture ---\n%s" % (detail, text))
        if marker is not None:
            self.assertFalse(os.path.exists(marker), "the body ran")
        return verdict, detail

    def test_F10_an_async_only_file_is_unverified_and_never_ran(self):
        m = self.marker()
        self.assertNeverRan(self.ASYNC_ONLY + "\nasync def test_Q_mark():\n    open(%r, 'w').write('x')\n" % m, m)

    def test_F10_a_generator_only_file_is_unverified_and_never_ran(self):
        for body in ("def test_Q_add():\n    assert 1 == 2, 'not built'\n    yield\n",
                     "def test_Q_add():\n    yield 1\n",
                     "async def test_Q_add():\n    assert 1 == 2, 'not built'\n    yield 1\n"):
            with self.subTest(body=body):
                self.assertNeverRan(body)

    def test_F10_an_async_function_that_would_raise_an_error_beside_a_red_function_is_unverified(self):
        self.assertNeverRan(FN_RED + "async def test_Q_other():\n    raise RuntimeError('x')\n")
        self.assertNeverRan(FN_RED + "def test_Q_gen():\n    raise RuntimeError('x')\n    yield\n")

    def test_F10_a_red_function_beside_an_async_one_that_would_fail_an_assertion_is_unverified(self):
        self.assertNeverRan(FN_RED + "async def test_Q_other():\n    assert False, 'would fail'\n")
        self.assertNeverRan(RED_FAIL + "\nasync def test_Q_other():\n    assert False, 'would fail'\n")

    def test_F10_a_functools_wraps_wrapper_returning_a_coroutine_is_unverified(self):
        self.assertNeverRan("import functools\n\ndef deco(f):\n    @functools.wraps(f)\n    def wrapper():\n        return f()\n"
                            "    return wrapper\n\n@deco\nasync def test_Q_wrapped():\n    assert False, 'would fail'\n\n" + FN_RED)

    def test_F10_a_function_returning_a_value_beside_a_red_function_stays_red(self):
        for value in ("True", "1"):
            with self.subTest(value=value):
                self.assertVerdict("red", "def test_Q_value():\n    return %s\n\n" % value + FN_RED)

    def test_F10_a_function_returning_a_value_with_nothing_failing_stays_green(self):
        self.assertVerdict("green", "def test_Q_value():\n    return True\n\ndef test_Q_num():\n    return 1\n\n" + FN_GREEN)


    # F11 a collected function whose body never ran is an error even under @unittest.expectedFailure
    def test_F11_an_expected_failure_async_only_file_is_unverified_and_never_ran(self):
        m = self.marker()
        self.assertNeverRan(HEAD + "\n@unittest.expectedFailure\nasync def test_Q_add():\n    assert 1 == 2, 'not built'\n"
                            "\n@unittest.expectedFailure\nasync def test_Q_mark():\n    open(%r, 'w').write('x')\n" % m, m)

    def test_F11_an_expected_failure_generator_beside_a_red_function_is_unverified(self):
        m = self.marker()
        self.assertNeverRan(HEAD + "\n" + FN_RED + "\n@unittest.expectedFailure\ndef test_Q_gen():\n"
                            "    open(%r, 'w').write('x')\n    assert False, 'would fail'\n    yield\n" % m, m)
        self.assertNeverRan(RED_FAIL + "\n@unittest.expectedFailure\ndef test_Q_gen():\n    yield 1\n")

    def test_F11_an_expected_failure_async_generator_is_unverified(self):
        m = self.marker()
        self.assertNeverRan(HEAD + "\n@unittest.expectedFailure\nasync def test_Q_agen():\n"
                            "    open(%r, 'w').write('x')\n    assert False, 'would fail'\n    yield 1\n" % m, m)
        self.assertNeverRan(HEAD + "\n" + FN_RED + "\n@unittest.expectedFailure\nasync def test_Q_agen():\n    yield 1\n")

    def test_F11_an_expected_failure_flag_copied_by_functools_wraps_onto_an_async_function_is_unverified(self):
        m = self.marker()
        deco = ("import functools\nimport unittest\n\ndef deco(f):\n    @functools.wraps(f)\n    def wrapper():\n        return f()\n"
                "    return wrapper\n\n")
        self.assertNeverRan(deco + "@deco\n@unittest.expectedFailure\nasync def test_Q_wrapped():\n"
                            "    open(%r, 'w').write('x')\n    assert False, 'would fail'\n" % m, m)
        self.assertNeverRan(deco + "@deco\n@unittest.expectedFailure\nasync def test_Q_wrapped():\n    assert False, 'would fail'\n\n"
                            + FN_RED)

    def test_F11_an_expected_failure_sync_function_failing_an_assertion_stays_green(self):
        self.assertVerdict("green", HEAD + "\n@unittest.expectedFailure\ndef test_Q_add():\n    assert False, 'expected'\n")
        self.assertVerdict("green", HEAD + "\n@unittest.expectedFailure\ndef test_Q_add():\n    assert False, 'expected'\n\n" + FN_GREEN)


    # F12 under @unittest.expectedFailure any exception is an expected failure — for a function as for a TestCase method
    XFAIL_FN = HEAD + "\n@unittest.expectedFailure\ndef test_Q_other():\n    add(1)\n\n"
    XFAIL_TC = HEAD + "class X(unittest.TestCase):\n    @unittest.expectedFailure\n    def test_Q_other(self):\n        add(1)\n\n"

    def test_F12_an_expected_failure_function_raising_name_error_beside_a_red_function_is_red(self):
        self.assertVerdict("red", self.XFAIL_FN + FN_RED)

    def test_F12_an_expected_failure_function_raising_name_error_alone_is_green(self):
        self.assertVerdict("green", self.XFAIL_FN)

    def test_F12_an_expected_failure_testcase_method_raising_name_error_gives_the_same_verdicts(self):
        self.assertVerdict("red", self.XFAIL_TC + FN_RED)
        self.assertVerdict("green", self.XFAIL_TC)


    # F13 the bound object's own signature decides whether a test_* function is collected
    MOCK = "from unittest import mock\n\n"
    WRAPS = ("import functools\n\ndef deco(f):\n    @functools.wraps(f)\n    def wrapper(*args, **kwargs):\n"
             "        return f(*args, **kwargs)\n    return wrapper\n\n")

    def test_F13_a_mock_patch_function_failing_an_assertion_alone_is_red(self):
        self.assertVerdict("red", self.MOCK + "@mock.patch(\"os.getcwd\")\ndef test_Q_add(getcwd):\n    assert False\n")

    def test_F13_a_mock_patch_function_failing_an_assertion_beside_a_passing_function_is_red(self):
        self.assertVerdict("red", self.MOCK + "@mock.patch(\"os.getcwd\")\ndef test_Q_add(getcwd):\n    assert False\n\n" + FN_GREEN)

    def test_F13_a_passing_mock_patch_function_beside_a_red_function_is_red(self):
        self.assertVerdict("red", self.MOCK + "@mock.patch(\"os.getcwd\")\ndef test_Q_patched(getcwd):\n"
                           "    import os\n    assert os.getcwd is getcwd\n\n" + FN_RED)

    def test_F13_a_mock_patch_function_is_called_with_the_mock(self):
        m = self.marker()
        self.assertVerdict("red", self.MOCK + "@mock.patch(\"os.getcwd\")\ndef test_Q_patched(getcwd):\n"
                           "    import os\n    if os.getcwd is getcwd:\n        open(%r, 'w').write('x')\n\n" % m + FN_RED)
        self.assertTrue(os.path.exists(m), "the mock.patch-decorated function was not called with its mock")

    def test_F13_a_wraps_wrapper_around_an_argument_needing_function_is_an_error_not_a_drop(self):
        verdict, detail = self.assertErrorVerdict(self.WRAPS + "@deco\ndef test_Q_needs(tmp_path):\n    assert tmp_path\n\n" + FN_GREEN)
        self.assertIn("TypeError", detail, "the TypeError is not reported: %s" % detail)

    def test_F13_a_plain_argument_needing_function_beside_a_red_function_is_still_not_collected(self):
        self.assertVerdict("red", "def test_Q_needs(tmp_path):\n    raise RuntimeError(tmp_path)\n\n" + FN_RED)


    # F14 a module-level def/async def statement in the file's own source makes the bound object the file's own
    DECO_FX = ("def deco(f):\n    def wrapper():\n        return f()\n    return wrapper\n\n"
               "def deco_arg(f):\n    def wrapper(a):\n        return f()\n    return wrapper\n")
    DECO_FILES = {"helper_fx.py": DECO_FX}
    FROM_DECO = "from helper_fx import deco, deco_arg\n\n"

    def test_F14_a_foreign_wrapper_without_wraps_failing_an_assertion_alone_is_red(self):
        self.assertVerdict("red", self.FROM_DECO + "@deco\ndef test_Q_add():\n    assert False\n", files=self.DECO_FILES)

    def test_F14_a_foreign_wrapper_without_wraps_failing_an_assertion_beside_a_passing_function_is_red(self):
        self.assertVerdict("red", self.FROM_DECO + "@deco\ndef test_Q_add():\n    assert False\n\n" + FN_GREEN, files=self.DECO_FILES)

    def test_F14_a_foreign_wrapper_is_called_and_its_body_runs(self):
        m = self.marker()
        self.assertVerdict("red", self.FROM_DECO + "@deco\ndef test_Q_mark():\n    open(%r, 'w').write('x')\n\n" % m + FN_RED,
                           files=self.DECO_FILES)
        self.assertTrue(os.path.exists(m), "the function decorated by a foreign wrapper was not called")

    def test_F14_a_foreign_wrapper_raising_an_error_is_an_error_not_a_drop(self):
        self.assertErrorVerdict(self.FROM_DECO + "@deco\ndef test_Q_other():\n    raise RuntimeError('x')\n\n" + FN_RED,
                                files=self.DECO_FILES)

    def test_F14_functools_cache_on_a_function_failing_an_assertion_is_red(self):
        self.assertVerdict("red", "import functools\n\n@functools.cache\ndef test_Q_add():\n    assert False\n")
        self.assertVerdict("red", "import functools\n\n@functools.cache\ndef test_Q_add():\n    assert False\n\n" + FN_GREEN)

    def assertNeverRanWith(self, text, files, marker=None):
        verdict, detail = self.assertVerdict("unverified", text, files=files)
        self.assertNotIn(NO_TESTS_RAN, detail, "the functions were not collected: %s\n--- fixture ---\n%s" % (detail, text))
        self.assertIn("never ran", detail, "the detail does not say the body never ran: %s\n--- fixture ---\n%s" % (detail, text))
        if marker is not None:
            self.assertFalse(os.path.exists(marker), "the body ran")

    def test_F14_a_foreign_wrapper_around_an_async_function_is_unverified_and_never_ran(self):
        m = self.marker()
        self.assertNeverRanWith(self.FROM_DECO + "@deco\nasync def test_Q_add():\n    open(%r, 'w').write('x')\n    assert False\n" % m,
                                self.DECO_FILES, m)
        self.assertNeverRanWith(self.FROM_DECO + "@deco\nasync def test_Q_other():\n    assert False\n\n" + FN_RED, self.DECO_FILES)

    def test_F14_a_foreign_wrapper_needing_an_argument_beside_a_red_function_is_not_collected(self):
        self.assertVerdict("red", self.FROM_DECO + "@deco_arg\ndef test_Q_needs():\n    raise RuntimeError('x')\n\n" + FN_RED,
                           files=self.DECO_FILES)

    def test_F14_a_foreign_wrapper_needing_an_argument_alone_has_no_tests(self):
        verdict, detail = self.assertVerdict("unverified", self.FROM_DECO + "@deco_arg\ndef test_Q_needs():\n    assert False\n",
                                             rel="checks/probe.py", files=self.DECO_FILES)
        for word in ("unittest", "TestCase", "test_"):
            self.assertIn(word, detail)

    def test_F14_a_decorator_returning_a_non_callable_beside_a_passing_function_is_green(self):
        self.assertVerdict("green", "@(lambda f: None)\ndef test_Q_gone():\n    raise RuntimeError('x')\n\n"
                           "@(lambda f: 1)\ndef test_Q_one():\n    assert False\n\n" + FN_GREEN)

    def test_F14_imported_names_stay_uncollected_beside_a_top_level_def_of_another_name(self):
        files = {"helper_fx.py": self.HELPER}
        self.assertVerdict("green", "from helper_fx import test_x\n\n" + FN_GREEN, files=files)
        self.assertVerdict("green", "import helper_fx\ntest_y = helper_fx.test_z\n\n" + FN_GREEN, files=files)
        self.assertVerdict("red", "from helper_fx import test_x\nimport helper_fx\ntest_y = helper_fx.test_z\n\n" + FN_RED, files=files)

    # F15 defined in this file, by identity: the bound object is, or wraps, a function compiled from this file
    PRE_FX = ("def pre(f):\n    def wrapper():\n        assert False, 'precondition'\n        return f()\n    return wrapper\n")
    HELPER_FILES = {"helper_fx.py": HELPER + "\n" + DECO_FX + "\n" + PRE_FX}

    def test_F15_a_def_rebound_by_from_import_to_an_imported_red_function_beside_a_passing_function_is_green(self):
        self.assertVerdict("green", "def test_x():\n    pass\n\nfrom helper_fx import test_x\n\n" + FN_GREEN, files=self.HELPER_FILES)

    def test_F15_a_def_rebound_by_from_import_beside_an_own_red_function_is_red(self):
        self.assertVerdict("red", "def test_x():\n    pass\n\nfrom helper_fx import test_x\n\n" + FN_RED, files=self.HELPER_FILES)

    def test_F15_a_def_rebound_to_an_imported_erroring_function_adds_nothing_to_an_own_red_function(self):
        self.assertVerdict("red", "def test_z():\n    pass\n\nfrom helper_fx import test_z\n\n" + FN_RED, files=self.HELPER_FILES)

    def test_F15_a_def_rebound_by_assignment_to_an_imported_red_function_is_not_collected(self):
        self.assertVerdict("green", "import helper_fx\n\ndef test_y():\n    pass\n\ntest_y = helper_fx.test_x\n\n" + FN_GREEN,
                           files=self.HELPER_FILES)
        self.assertVerdict("red", "import helper_fx\n\ndef test_y():\n    pass\n\ntest_y = helper_fx.test_z\n\n" + FN_RED,
                           files=self.HELPER_FILES)

    def test_F15_a_def_rebound_by_a_star_import_is_not_collected(self):
        self.assertVerdict("green", "def test_x():\n    pass\n\nfrom helper_fx import *\n\n" + FN_GREEN, files=self.HELPER_FILES)
        self.assertVerdict("red", "def test_z():\n    pass\n\nfrom helper_fx import *\n\n" + FN_RED, files=self.HELPER_FILES)

    def test_F15_a_foreign_wrapper_inside_a_module_level_if_failing_an_assertion_is_red(self):
        body = self.FROM_DECO + "if True:\n    @deco\n    def test_Q_add():\n        assert False\n"
        self.assertVerdict("red", body + "\n" + FN_GREEN, files=self.HELPER_FILES)
        self.assertVerdict("red", body, files=self.HELPER_FILES)

    def test_F15_a_foreign_wrapper_inside_a_module_level_try_failing_an_assertion_is_red(self):
        body = self.FROM_DECO + "try:\n    @deco\n    def test_Q_add():\n        assert False\nexcept ImportError:\n    pass\n"
        self.assertVerdict("red", body + "\n" + FN_GREEN, files=self.HELPER_FILES)
        self.assertVerdict("red", body, files=self.HELPER_FILES)

    def test_F15_a_foreign_wrapper_inside_a_module_level_with_failing_an_assertion_is_red(self):
        body = (self.FROM_DECO + "import contextlib\n\nwith contextlib.nullcontext():\n"
                "    @deco\n    def test_Q_add():\n        assert False\n")
        self.assertVerdict("red", body + "\n" + FN_GREEN, files=self.HELPER_FILES)
        self.assertVerdict("red", body, files=self.HELPER_FILES)

    def test_F15_a_foreign_wrapper_inside_a_module_level_if_is_called_and_its_body_runs(self):
        m = self.marker()
        self.assertVerdict("red", self.FROM_DECO + "if True:\n    @deco\n    def test_Q_mark():\n        open(%r, 'w').write('x')\n\n" % m
                           + FN_RED, files=self.HELPER_FILES)
        self.assertTrue(os.path.exists(m), "the decorated function inside a module-level if was not called")

    def test_F15_functools_cache_inside_a_module_level_if_failing_an_assertion_is_red(self):
        body = "import functools\n\nif True:\n    @functools.cache\n    def test_Q_add():\n        assert False\n"
        self.assertVerdict("red", body + "\n" + FN_GREEN)
        self.assertVerdict("red", body)

    def test_F15_foreign_wrappers_stacked_three_deep_are_followed_and_red(self):
        self.assertVerdict("red", self.FROM_DECO + "@deco\n@deco\n@deco\ndef test_Q_add():\n    assert False\n\n" + FN_GREEN,
                           files=self.HELPER_FILES)

    def test_F15_a_wrapper_the_file_defines_around_an_imported_red_function_is_red(self):
        self.assertVerdict("red", "import helper_fx\n\ndef mine(f):\n    def w():\n        return f()\n    return w\n\n"
                           "test_y = mine(helper_fx.test_x)\n\n" + FN_GREEN, files=self.HELPER_FILES)

    def test_F15_a_helper_decorator_whose_wrapper_asserts_before_calling_the_test_is_red(self):
        self.assertVerdict("red", "from helper_fx import pre\n\n@pre\ndef test_Q_add():\n    pass\n\n" + FN_GREEN, files=self.HELPER_FILES)

    def test_F15_F1_imported_and_assigned_functions_are_still_not_collected(self):
        self.assertVerdict("green", "from helper_fx import test_x\n\n" + FN_GREEN, files=self.HELPER_FILES)
        self.assertVerdict("green", "import helper_fx\ntest_v = helper_fx.test_w\n\n" + FN_GREEN, files=self.HELPER_FILES)
        self.assertVerdict("green", "from helper_fx import *\n\n" + FN_GREEN, files=self.HELPER_FILES)

    def test_F15_F1_a_class_a_callable_object_and_a_partial_over_a_local_function_are_still_not_collected(self):
        self.assertVerdict("green", "class test_thing:\n    def __init__(self):\n        raise AssertionError('class')\n\n" + FN_GREEN)
        self.assertVerdict("green", "class Boom:\n    def __call__(self):\n        raise AssertionError('callable')\n\n"
                           "test_obj = Boom()\n\n" + FN_GREEN)
        self.assertVerdict("green", "import functools\n\ndef boom():\n    raise AssertionError('partial')\n\n"
                           "test_partial = functools.partial(boom)\n\n" + FN_GREEN)

    # F16 more links (a bound method's __func__, an instance's own attributes); inspection never escapes the loader
    RETRY_FX = ("class retry:\n    def __init__(self, f):\n        self.f = f\n\n    def __call__(self):\n        return self.f()\n")
    FOREIGN_FX = ("class Foreign:\n    def run(self):\n        assert False, 'foreign method'\n")
    F16_FILES = {"helper_fx.py": HELPER + "\n" + DECO_FX + "\n" + PRE_FX + "\n" + RETRY_FX + "\n" + FOREIGN_FX}
    FROM_RETRY = "from helper_fx import retry\n\n"

    def test_F16_a_class_based_decorator_without_update_wrapper_failing_an_assertion_alone_is_red(self):
        self.assertVerdict("red", self.FROM_RETRY + "@retry\ndef test_Q_add():\n    assert False\n", files=self.F16_FILES)

    def test_F16_a_class_based_decorator_without_update_wrapper_beside_a_passing_function_is_red(self):
        self.assertVerdict("red", self.FROM_RETRY + "@retry\ndef test_Q_add():\n    assert False\n\n" + FN_GREEN,
                           files=self.F16_FILES)

    def test_F16_a_class_based_decorator_is_called_and_its_body_runs(self):
        m = self.marker()
        self.assertVerdict("red", self.FROM_RETRY + "@retry\ndef test_Q_mark():\n    open(%r, 'w').write('x')\n\n" % m + FN_RED,
                           files=self.F16_FILES)
        self.assertTrue(os.path.exists(m), "the function held by a class-based decorator was not called")

    def test_F16_a_bound_method_of_a_class_the_file_defines_failing_an_assertion_is_red(self):
        body = "class Checks:\n    def run(self):\n        assert False\n\ntest_Q_run = Checks().run\n"
        self.assertVerdict("red", body)
        self.assertVerdict("red", body + "\n" + FN_GREEN)

    def test_F16_a_bound_method_of_a_class_from_the_helper_module_beside_a_passing_function_is_green(self):
        self.assertVerdict("green", "from helper_fx import Foreign\n\ntest_Q_run = Foreign().run\n\n" + FN_GREEN, files=self.F16_FILES)

    def test_F16_F1_a_partial_over_a_local_function_and_a_callable_object_holding_no_function_are_still_not_collected(self):
        self.assertVerdict("green", "import functools\n\ndef boom():\n    raise AssertionError('partial')\n\n"
                           "test_partial = functools.partial(boom)\n\n" + FN_GREEN)
        self.assertVerdict("green", "class Boom:\n    def __init__(self):\n        self.n = 1\n        self.name = 'x'\n\n"
                           "    def __call__(self):\n        raise AssertionError('callable')\n\n"
                           "test_obj = Boom()\n\n" + FN_GREEN)
        self.assertVerdict("green", "import helper_fx\n\nclass Holder:\n    def __init__(self):\n        self.f = helper_fx.test_x\n\n"
                           "    def __call__(self):\n        return self.f()\n\ntest_held = Holder()\n\n" + FN_GREEN,
                           files=self.F16_FILES)

    CFG_KEYERROR = ("class Cfg:\n    def __call__(self):\n        pass\n\n"
                    "    def __getattr__(self, name):\n        raise KeyError(name)\n\ntest_config = Cfg()\n\n")
    CFG_RUNTIME = ("class Cfg:\n    def __call__(self):\n        pass\n\n"
                   "    def __getattr__(self, name):\n        raise RuntimeError(name)\n\ntest_config = Cfg()\n\n")
    CFG_CLASS = ("class Cfg:\n    def __call__(self):\n        pass\n\n"
                 "    @property\n    def __class__(self):\n        raise RuntimeError('__class__')\n\ntest_config = Cfg()\n\n")

    def test_F16_an_object_whose_getattr_raises_key_error_beside_a_red_function_is_red(self):
        self.assertVerdict("red", self.CFG_KEYERROR + FN_RED)

    def test_F16_an_object_whose_getattr_raises_key_error_beside_a_passing_function_is_green(self):
        self.assertVerdict("green", self.CFG_KEYERROR + FN_GREEN)

    def test_F16_an_object_whose_getattr_raises_runtime_error_beside_a_red_function_is_red(self):
        self.assertVerdict("red", self.CFG_RUNTIME + FN_RED)

    def test_F16_an_object_whose_getattr_raises_runtime_error_beside_a_passing_function_is_green(self):
        self.assertVerdict("green", self.CFG_RUNTIME + FN_GREEN)

    def test_F16_an_object_whose_class_property_raises_runtime_error_beside_a_red_function_is_red(self):
        self.assertVerdict("red", self.CFG_CLASS + FN_RED)

    def test_F16_an_object_whose_class_property_raises_runtime_error_beside_a_passing_function_is_green(self):
        self.assertVerdict("green", self.CFG_CLASS + FN_GREEN)

    # F17a each link is guarded: an exception on one link skips that link only; F17b expectedFailure along the path
    PROXY_FX = ("class Client:\n    def __call__(self):\n        return None\n\n"
                "    @property\n    def __class__(self):\n        raise RuntimeError('__class__')\n\n"
                "def deco_proxy(fn):\n    client = Client()\n\n    def wrapper():\n        return fn(client)\n    return wrapper\n")
    F17_FILES = {"helper_fx.py": HELPER + "\n" + DECO_FX + "\n" + PRE_FX + "\n" + RETRY_FX + "\n" + FOREIGN_FX + "\n" + PROXY_FX}
    FROM_PROXY = "from helper_fx import deco_proxy\n\n"
    XFAIL_BODY = "@unittest.expectedFailure\ndef test_Q_add():\n    assert False\n"

    def test_F17_the_proxy_fixture_puts_the_raising_client_in_the_first_closure_cell(self):
        d = self.tmp()
        self.write(d, "helper_fx.py", self.F17_FILES["helper_fx.py"])
        out = subprocess.run([sys.executable, "-c", "import helper_fx\nw = helper_fx.deco_proxy(len)\n"
                              "print(w.__code__.co_freevars)\ntry:\n    w.__closure__[0].cell_contents.__class__\n"
                              "except RuntimeError:\n    print('raises')\n"], cwd=d, capture_output=True, text=True)
        self.assertEqual(out.stdout.split("\n")[:2], ["('client', 'fn')", "raises"], out)

    def test_F17_a_wrapper_whose_closure_holds_a_raising_client_before_fn_alone_is_red(self):
        self.assertVerdict("red", self.FROM_PROXY + "@deco_proxy\ndef test_Q_add(c):\n    assert False\n", files=self.F17_FILES)

    def test_F17_a_wrapper_whose_closure_holds_a_raising_client_before_fn_beside_a_passing_function_is_red(self):
        self.assertVerdict("red", self.FROM_PROXY + "@deco_proxy\ndef test_Q_add(c):\n    assert False\n\n" + FN_GREEN,
                           files=self.F17_FILES)

    def test_F17_a_wrapper_whose_closure_holds_a_raising_client_is_called_and_its_body_runs(self):
        m = self.marker()
        self.assertVerdict("red", self.FROM_PROXY + "@deco_proxy\ndef test_Q_mark(c):\n    open(%r, 'w').write('x')\n\n" % m
                           + FN_RED, files=self.F17_FILES)
        self.assertTrue(os.path.exists(m), "the function behind a wrapper whose closure holds a raising client was not called")

    def test_F17_a_closure_wrapper_without_wraps_over_an_expected_failure_alone_is_green(self):
        self.assertVerdict("green", HEAD + self.FROM_DECO + "@deco\n" + self.XFAIL_BODY, files=self.F17_FILES)

    def test_F17_a_closure_wrapper_without_wraps_over_an_expected_failure_beside_a_passing_function_is_green(self):
        self.assertVerdict("green", HEAD + self.FROM_DECO + "@deco\n" + self.XFAIL_BODY + "\n" + FN_GREEN, files=self.F17_FILES)

    def test_F17_a_class_based_decorator_over_an_expected_failure_alone_is_green(self):
        self.assertVerdict("green", HEAD + self.FROM_RETRY + "@retry\n" + self.XFAIL_BODY, files=self.F17_FILES)

    def test_F17_a_class_based_decorator_over_an_expected_failure_beside_a_passing_function_is_green(self):
        self.assertVerdict("green", HEAD + self.FROM_RETRY + "@retry\n" + self.XFAIL_BODY + "\n" + FN_GREEN, files=self.F17_FILES)

    def test_F17_a_wrapped_expected_failure_beside_an_own_red_function_is_still_red(self):
        self.assertVerdict("red", HEAD + self.FROM_DECO + "@deco\n" + self.XFAIL_BODY.replace("test_Q_add", "test_Q_other")
                           + "\n" + FN_RED, files=self.F17_FILES)
        self.assertVerdict("red", HEAD + self.FROM_RETRY + "@retry\n" + self.XFAIL_BODY.replace("test_Q_add", "test_Q_other")
                           + "\n" + FN_RED, files=self.F17_FILES)

    def test_F17_F11_a_foreign_wrapper_over_an_expected_failure_async_function_is_unverified_and_never_ran(self):
        m = self.marker()
        self.assertNeverRanWith(HEAD + self.FROM_DECO + "@deco\n@unittest.expectedFailure\nasync def test_Q_add():\n"
                                "    open(%r, 'w').write('x')\n    assert False\n" % m, self.F17_FILES, m)
        self.assertNeverRanWith(HEAD + self.FROM_DECO + "@deco\n@unittest.expectedFailure\nasync def test_Q_other():\n"
                                "    assert False\n\n" + FN_GREEN, self.F17_FILES)

    def test_F17_a_foreign_wrapper_over_a_plain_failing_function_without_the_flag_is_still_red(self):
        self.assertVerdict("red", HEAD + self.FROM_DECO + "@deco\ndef test_Q_add():\n    assert False\n", files=self.F17_FILES)
        self.assertVerdict("red", HEAD + self.FROM_RETRY + "@retry\ndef test_Q_add():\n    assert False\n\n" + FN_GREEN,
                           files=self.F17_FILES)

    # F18 the expectedFailure flag is searched along every link, whether or not the bound object is compiled from the file
    OWN_DECO = "def mydeco(f):\n    def w():\n        return f()\n    return w\n\n"
    OWN_DECO2 = "def outer(f):\n    def w2():\n        return f()\n    return w2\n\n"
    OWN_RETRY = "class myretry:\n    def __init__(self, f):\n        self.f = f\n\n    def __call__(self):\n        return self.f()\n\n"

    def test_F18_a_wrapper_the_file_defines_over_an_expected_failure_alone_is_green(self):
        self.assertVerdict("green", HEAD + "\n" + self.OWN_DECO + "@mydeco\n" + self.XFAIL_BODY)

    def test_F18_a_wrapper_the_file_defines_over_an_expected_failure_beside_an_own_passing_function_is_green(self):
        self.assertVerdict("green", HEAD + "\n" + self.OWN_DECO + "@mydeco\n" + self.XFAIL_BODY + "\n" + FN_GREEN)

    def test_F18_two_stacked_wrappers_the_file_defines_over_an_expected_failure_are_green(self):
        self.assertVerdict("green", HEAD + "\n" + self.OWN_DECO + self.OWN_DECO2 + "@outer\n@mydeco\n" + self.XFAIL_BODY)
        self.assertVerdict("green", HEAD + "\n" + self.OWN_DECO + self.OWN_DECO2 + "@outer\n@mydeco\n" + self.XFAIL_BODY
                           + "\n" + FN_GREEN)

    def test_F18_a_class_based_decorator_the_file_defines_over_an_expected_failure_is_green(self):
        self.assertVerdict("green", HEAD + "\n" + self.OWN_RETRY + "@myretry\n" + self.XFAIL_BODY)
        self.assertVerdict("green", HEAD + "\n" + self.OWN_RETRY + "@myretry\n" + self.XFAIL_BODY + "\n" + FN_GREEN)

    def test_F18_a_wrapper_the_file_defines_over_a_flagless_failing_function_is_still_red(self):
        self.assertVerdict("red", HEAD + "\n" + self.OWN_DECO + "@mydeco\ndef test_Q_add():\n    assert False\n")
        self.assertVerdict("red", HEAD + "\n" + self.OWN_DECO + "@mydeco\ndef test_Q_add():\n    assert False\n\n" + FN_GREEN)

    def test_F18_F11_a_wrapper_the_file_defines_over_an_expected_failure_async_function_is_unverified_and_never_ran(self):
        m = self.marker()
        self.assertNeverRanWith(HEAD + "\n" + self.OWN_DECO + "@mydeco\n@unittest.expectedFailure\nasync def test_Q_add():\n"
                                "    open(%r, 'w').write('x')\n    assert False\n" % m, None, m)
        self.assertNeverRanWith(HEAD + "\n" + self.OWN_DECO + "@mydeco\n@unittest.expectedFailure\nasync def test_Q_other():\n"
                                "    assert False\n\n" + FN_GREEN, None)

    # F19 the mark is a function's: a non-function object reached on the way is followed, never asked for the mark
    EVERYTHING_FX = ("class Everything:\n    def __call__(self, *a):\n        return self\n\n"
                     "    def __getattr__(self, name):\n        return Everything()\n\n"
                     "def deco_everything(fn):\n    client = Everything()\n\n    def wrapper():\n        return fn(client)\n    return wrapper\n\n"
                     "class retry_everything:\n    def __init__(self, f):\n        self.f = f\n\n    def __call__(self):\n        return self.f()\n\n"
                     "    def __getattr__(self, name):\n        return Everything()\n")
    F19_FILES = {"helper_fx.py": HELPER + "\n" + DECO_FX + "\n" + PRE_FX + "\n" + RETRY_FX + "\n" + FOREIGN_FX + "\n" + PROXY_FX
                 + "\n" + EVERYTHING_FX}
    FROM_EVERYTHING = "from helper_fx import deco_everything, retry_everything\n\n"
    OWN_EVERYTHING = ("class Everything:\n    def __call__(self, *a):\n        return self\n\n"
                      "    def __getattr__(self, name):\n        return Everything()\n\n"
                      "class myretry_everything:\n    def __init__(self, f):\n        self.f = f\n\n    def __call__(self):\n        return self.f()\n\n"
                      "    def __getattr__(self, name):\n        return Everything()\n\n"
                      "def mydeco_everything(fn):\n    client = Everything()\n\n    def wrapper():\n        return fn(client)\n    return wrapper\n\n")

    def test_F19_the_everything_fixture_answers_the_mark_truthily_from_a_closure_cell_and_a_decorator_instance(self):
        d = self.tmp()
        self.write(d, "helper_fx.py", self.F19_FILES["helper_fx.py"])
        out = subprocess.run([sys.executable, "-c", "import inspect, helper_fx\n"
                              "w = helper_fx.deco_everything(len)\nprint(w.__code__.co_freevars)\n"
                              "c = w.__closure__[0].cell_contents\n"
                              "print(bool(getattr(c, '__unittest_expecting_failure__', False)), inspect.isfunction(c))\n"
                              "r = helper_fx.retry_everything(len)\n"
                              "print(bool(getattr(r, '__unittest_expecting_failure__', False)), inspect.isfunction(r))\n"],
                             cwd=d, capture_output=True, text=True)
        self.assertEqual(out.stdout.split("\n")[:3], ["('client', 'fn')", "True False", "True False"], out)

    def test_F19_a_helper_wrapper_closing_over_an_everything_proxy_over_a_flagless_failing_function_alone_is_red(self):
        self.assertVerdict("red", self.FROM_EVERYTHING + "@deco_everything\ndef test_Q_add(c):\n    assert False\n",
                           files=self.F19_FILES)

    def test_F19_a_helper_wrapper_closing_over_an_everything_proxy_over_a_flagless_failing_function_beside_a_passing_function_is_red(self):
        self.assertVerdict("red", self.FROM_EVERYTHING + "@deco_everything\ndef test_Q_add(c):\n    assert False\n\n" + FN_GREEN,
                           files=self.F19_FILES)

    def test_F19_a_helper_wrapper_closing_over_an_everything_proxy_over_a_name_error_beside_an_own_red_function_is_unverified(self):
        self.assertErrorVerdict(self.FROM_EVERYTHING + "@deco_everything\ndef test_Q_other(c):\n    add(1)\n\n" + FN_RED,
                                files=self.F19_FILES)

    def test_F19_a_file_defined_wrapper_closing_over_an_everything_proxy_over_a_flagless_failing_function_is_red(self):
        self.assertVerdict("red", self.OWN_EVERYTHING + "@mydeco_everything\ndef test_Q_add(c):\n    assert False\n")
        self.assertErrorVerdict(self.OWN_EVERYTHING + "@mydeco_everything\ndef test_Q_other(c):\n    add(1)\n\n" + FN_RED)

    def test_F19_a_class_based_decorator_whose_getattr_answers_every_name_over_a_flagless_failing_function_alone_is_red(self):
        self.assertVerdict("red", self.FROM_EVERYTHING + "@retry_everything\ndef test_Q_add():\n    assert False\n",
                           files=self.F19_FILES)

    def test_F19_a_class_based_decorator_whose_getattr_answers_every_name_over_a_flagless_failing_function_beside_a_passing_function_is_red(self):
        self.assertVerdict("red", self.FROM_EVERYTHING + "@retry_everything\ndef test_Q_add():\n    assert False\n\n" + FN_GREEN,
                           files=self.F19_FILES)

    def test_F19_a_file_defined_class_based_decorator_whose_getattr_answers_every_name_over_a_flagless_failing_function_is_red(self):
        self.assertVerdict("red", self.OWN_EVERYTHING + "@myretry_everything\ndef test_Q_add():\n    assert False\n")
        self.assertVerdict("red", self.OWN_EVERYTHING + "@myretry_everything\ndef test_Q_add():\n    assert False\n\n" + FN_GREEN)

    def test_F19_a_class_based_decorator_whose_getattr_answers_every_name_over_a_name_error_beside_an_own_red_function_is_unverified(self):
        self.assertErrorVerdict(self.FROM_EVERYTHING + "@retry_everything\ndef test_Q_other():\n    add(1)\n\n" + FN_RED,
                                files=self.F19_FILES)

    def test_F19_F18_a_file_defined_wrapper_over_an_expected_failure_is_still_green(self):
        self.assertVerdict("green", HEAD + "\n" + self.OWN_DECO + "@mydeco\n" + self.XFAIL_BODY)
        self.assertVerdict("green", HEAD + "\n" + self.OWN_DECO + "@mydeco\n" + self.XFAIL_BODY + "\n" + FN_GREEN)

    def test_F19_F18_a_class_based_decorator_over_an_expected_failure_is_still_green(self):
        self.assertVerdict("green", HEAD + "\n" + self.OWN_RETRY + "@myretry\n" + self.XFAIL_BODY)
        self.assertVerdict("green", HEAD + self.FROM_RETRY + "@retry\n" + self.XFAIL_BODY + "\n" + FN_GREEN, files=self.F19_FILES)

    def test_F19_F18_a_foreign_wrapper_over_an_expected_failure_is_still_green(self):
        self.assertVerdict("green", HEAD + self.FROM_DECO + "@deco\n" + self.XFAIL_BODY, files=self.F19_FILES)

class G12FunctionsValidate(Gate):
    """worker.validate with worker.load_member("teujip") on temporary git projects holding function-style tests."""

    ANS = G4Validate.ANS
    run_validate = G4Validate.run_validate
    failed_with = G4Validate.failed_with

    def test_F8_a_red_function_file_passes(self):
        d = self.repo()
        before = worker.tree_state(d)
        self.write(d, "tests/test_x.py", FN_RED)
        out = self.run_validate(d, before)
        self.assertEqual(out["status"], "done", out)

    def test_F8_a_green_function_file_decides_nothing(self):
        d = self.repo()
        before = worker.tree_state(d)
        self.write(d, "tests/test_x.py", "def test_Q_add():\n    assert True\n")
        out = self.run_validate(d, before)
        self.failed_with(out, "red-before-build: tests/test_x.py passes before the build — it decides nothing")

    def test_F8_an_erroring_function_file_is_not_verified_red(self):
        d = self.repo()
        before = worker.tree_state(d)
        self.write(d, "tests/test_x.py", FN_RED + "def test_Q_other():\n    import app_not_built_q\n")
        out = self.run_validate(d, before)
        self.failed_with(out, "red-before-build: tests/test_x.py is not verified red — ")
        self.assertFalse(any(NO_TESTS_RAN in n for n in out["non-claims"]), out)

    def test_F8_a_support_file_defining_a_collected_function_is_refused(self):
        d = self.repo()
        before = worker.tree_state(d)
        self.write(d, "helper_fx.py", "VALUE = 1\n\ndef test_helper():\n    assert VALUE == 1\n")
        self.write(d, "tests/test_x.py", "from helper_fx import VALUE\n\ndef test_Q_add():\n    assert VALUE == 2\n")
        ans = dict(json.loads(json.dumps(self.ANS)), tests=["tests/test_x.py", "helper_fx.py"], support=["helper_fx.py"])
        out = self.run_validate(d, before, ans)
        self.failed_with(out, "red-before-build: helper_fx.py is declared support — it holds")

    def test_F8_a_support_helper_with_only_uncollected_functions_is_accepted(self):
        d = self.repo()
        before = worker.tree_state(d)
        self.write(d, "other_fx.py", "def test_imp(tmp_path):\n    assert False\n")   # needs an argument: not collected here either
        self.write(d, "helper_fx.py", "from other_fx import test_imp\nimport other_fx\ntest_alias = other_fx.test_imp\nVALUE = 1\n\n"
                   "def test_needs(tmp_path):\n    assert False\n\ndef check_value():\n    assert VALUE == 1\n")
        self.write(d, "tests/test_x.py", "from helper_fx import VALUE\n\ndef test_Q_add():\n    assert VALUE == 2\n")
        ans = dict(json.loads(json.dumps(self.ANS)), tests=["tests/test_x.py", "helper_fx.py", "other_fx.py"],
                   support=["helper_fx.py", "other_fx.py"])
        out = self.run_validate(d, before, ans)
        self.assertEqual(out["status"], "done", out)
        self.assertIn("support (protected with the tests, not red evidence): helper_fx.py, other_fx.py", out["non-claims"], out)


    def test_F10_an_async_only_file_is_not_verified_red(self):
        d = self.repo()
        before = worker.tree_state(d)
        self.write(d, "tests/test_x.py", G11Functions.ASYNC_ONLY)
        out = self.run_validate(d, before)
        self.failed_with(out, "red-before-build: tests/test_x.py is not verified red — ")
        self.assertFalse(any(NO_TESTS_RAN in n for n in out["non-claims"]), out)


if __name__ == "__main__":
    unittest.main()
