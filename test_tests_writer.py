"""hacheong 2.1.0 — the tests writer's gates, from guin-site's review (run-20261101-113600-3727).

  python3 -m unittest test_tests_writer.py

C: red-before-build's test execution context (request `test-context`, project hacheong/test-context.json).
S: `support` — protected artifacts the tests need that are not tests.
T: only-tests-touched tells wrote, read and unclear transcript mentions apart.

Everything is reached through worker's public entry points on fixture files in temporary git repositories; no model call,
no network, nothing written outside temporary directories.
"""
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.join(ROOT, "plugin")
sys.path.insert(0, PLUGIN)
import worker  # noqa: E402

REQUEST = {"artifact-type": "chongdae/request@1", "stage": "build", "run": "run-1", "task": "T1", "role": "nitpick", "target": ".",
           "goal": "g", "brief": "test it", "closes": ["Q-add"], "contract": {"Q-add": "## Q-add\n\n`add` appends."},
           "checks": [["python3", "-m", "unittest", "tests/test_x.py", "-k", "Q_add"]], "response": "./r.json"}
BUILD_REQUEST = dict(REQUEST, role="implementer", brief="make it")
GOOD_BUILD = {"status": "done", "summary": "added", "verified": [{"check": "python3 -m unittest tests/test_x.py -k Q_add", "exit": 0}],
              "decisions": [], "non-claims": []}

HEAD = "import unittest\n"
RED_FAIL = HEAD + "class T(unittest.TestCase):\n    def test_Q_add(self):\n        self.fail('not built')\n"
GREEN = HEAD + "class T(unittest.TestCase):\n    def test_Q_add(self):\n        self.assertEqual(1, 1)\n"
# a tests/ file importing its sibling at module top, as guin-site's do
SIBLING_RED = ("import unittest\nfrom support import VALUE\nclass T(unittest.TestCase):\n"
               "    def test_Q_add(self):\n        self.assertEqual(VALUE, 2, 'not built')\n")
SUPPORT = "VALUE = 1\n"

WROTE = "only-tests-touched: changed outside the tests it declared: "
NEVER = "changed during the call by another hand (this member's transcript never names them), not held against it: "


def stream(*events):
    return "\n".join(json.dumps(e) for e in events) + "\n"


def claude_stream(*tool_uses, result=None):
    evs = [{"type": "system", "subtype": "init", "model": "claude-t", "session_id": "s1"}]
    for name, inp in tool_uses:
        evs.append({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": name, "input": inp}]}})
    evs.append({"type": "result", "num_turns": len(tool_uses) + 1, "total_cost_usd": 0.01, "session_id": "s1",
                "structured_output": result or {}})
    return stream(*evs)


def codex_stream(*items):
    """Codex `--json`: ("cmd", command) → a command_execution wrapped in /bin/zsh -lc; ("raw", command) unwrapped;
    ("files", [paths]) → a file_change."""
    evs = []
    for i, (kind, val) in enumerate(items):
        if kind == "files":
            item = {"id": "item_%d" % i, "type": "file_change", "changes": [{"path": p, "kind": "update"} for p in val], "status": "completed"}
        else:
            cmd = "/bin/zsh -lc %s" % json.dumps(val) if kind == "cmd" else val
            item = {"id": "item_%d" % i, "type": "command_execution", "command": cmd, "aggregated_output": "", "exit_code": 0,
                    "status": "completed"}
        evs.append({"type": "item.completed", "item": item})
    return stream(*evs)


class Base(unittest.TestCase):

    def tmp(self):
        d = tempfile.mkdtemp(prefix="hacheong-tw-")
        self.addCleanup(shutil.rmtree, d, True)
        return d

    def write(self, root, rel, text):
        p = os.path.join(root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(text)
        return p

    def git(self, d, *args):
        subprocess.run(["git"] + list(args), cwd=d, check=True, capture_output=True)

    def repo(self, files=None):
        """A temp git repo whose `files` are committed — they exist before the call."""
        d = self.tmp()
        self.git(d, "init", "-q")
        self.git(d, "config", "user.email", "t@t")
        self.git(d, "config", "user.name", "t")
        self.write(d, "README.md", "# x\n")
        for rel, text in (files or {}).items():
            self.write(d, rel, text)
        self.git(d, "add", "-A")
        self.git(d, "commit", "-qm", "base")
        return d

    def wrapper(self, path, marker=None, body=None):
        """An executable interpreter wrapper: records that it ran, then execs this interpreter."""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            fh.write("#!/bin/sh\n")
            if body is not None:
                fh.write(body)
            else:
                if marker:
                    fh.write("echo ran >> '%s'\n" % marker)
                fh.write("exec '%s' \"$@\"\n" % sys.executable)
        os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        return path

    def answer(self, tests=("tests/test_x.py",), support=None, **kw):
        a = {"status": "done", "summary": "", "non-claims": [], "tests": list(tests),
             "covers": [{"section": "Q-add", "tests": ["test_Q_add"]}]}
        if support is not None:
            a["support"] = list(support)
        a.update(kw)
        return a

    def teujip(self, d, before, ans=None, request=None, stream_text="", host="claude-code"):
        try:
            out = worker.validate(json.loads(json.dumps(ans or self.answer())), worker.load_member("teujip"),
                                  json.loads(json.dumps(request or REQUEST)), d, stream_text, host, before)
        except Exception as e:  # an exception escaping validate is itself the failure (A1: none may escape)
            self.fail("validate raised %s: %s" % (type(e).__name__, e))
        self.assertIsInstance(out, dict, out)
        return out

    def ctx(self, **c):
        return dict(REQUEST, **{"test-context": c})

    # --- reading the answer -------------------------------------------------------------------------------------------
    def notes(self, out):
        return out.get("non-claims", [])

    def done(self, out):
        self.assertEqual(out["status"], "done", json.dumps(out, indent=1))

    def failed(self, out, validator):
        self.assertEqual(out["status"], "failed", json.dumps(out, indent=1))
        self.assertIn(validator, out.get("validation", {}).get("failed", []), json.dumps(out, indent=1))

    def unverified(self, out, path):
        """The detail of `red-before-build: <path> is not verified red — <detail>`."""
        prefix = "red-before-build: %s is not verified red — " % path
        hits = [n for n in self.notes(out) if n.startswith(prefix)]
        self.assertTrue(hits, "%s is not 'not verified red':\n%s" % (path, json.dumps(out, indent=1)))
        self.failed(out, "red-before-build")
        return hits[0][len(prefix):]

    def starting(self, out, prefix):
        hits = [n for n in self.notes(out) if n.startswith(prefix)]
        self.assertTrue(hits, "no non-claim starts %r:\n%s" % (prefix, json.dumps(out, indent=1)))
        return hits[0]

    def assertNamesContext(self, detail):
        low = detail.lower()
        self.assertTrue("test context" in low or "test-context" in low, "the detail does not name the test context: %r" % detail)


# ======================================================================================================================
# Q-context
# ======================================================================================================================

class C1Declarations(Base):

    def sibling_repo(self, extra=None):
        files = {"tests/support.py": SUPPORT}
        files.update(extra or {})
        return self.repo(files)

    def test_C1_default_context_is_the_root_and_a_sibling_import_is_not_red(self):
        d = self.sibling_repo()
        before = worker.tree_state(d)
        self.write(d, "tests/test_x.py", SIBLING_RED)
        detail = self.unverified(self.teujip(d, before), "tests/test_x.py")
        self.assertIn("No module named 'support'", detail)

    def test_C1_request_test_context_cwd_tests_is_red(self):
        d = self.sibling_repo()
        before = worker.tree_state(d)
        self.write(d, "tests/test_x.py", SIBLING_RED)
        self.done(self.teujip(d, before, request=self.ctx(cwd="tests")))

    def test_C1_project_test_context_file_cwd_tests_is_red(self):
        d = self.sibling_repo({"hacheong/test-context.json": json.dumps({"cwd": "tests"})})
        before = worker.tree_state(d)
        self.write(d, "tests/test_x.py", SIBLING_RED)
        self.done(self.teujip(d, before))

    def test_C1_the_requests_declaration_wins_over_the_projects(self):
        d = self.sibling_repo({"hacheong/test-context.json": json.dumps({"cwd": "."})})
        before = worker.tree_state(d)
        self.write(d, "tests/test_x.py", SIBLING_RED)
        self.done(self.teujip(d, before, request=self.ctx(cwd="tests")))
        d2 = self.sibling_repo({"hacheong/test-context.json": json.dumps({"cwd": "tests"})})
        before2 = worker.tree_state(d2)
        self.write(d2, "tests/test_x.py", SIBLING_RED)
        detail = self.unverified(self.teujip(d2, before2, request=self.ctx(cwd=".")), "tests/test_x.py")
        self.assertIn("No module named 'support'", detail)

    def test_C1_a_request_test_context_of_null_counts_as_absent(self):
        d = self.sibling_repo({"hacheong/test-context.json": json.dumps({"cwd": "tests"})})
        before = worker.tree_state(d)
        self.write(d, "tests/test_x.py", SIBLING_RED)
        self.done(self.teujip(d, before, request=dict(REQUEST, **{"test-context": None})))

    def test_C1_a_key_left_out_takes_its_default(self):
        # python only: cwd stays the root, so the sibling import fails; the declared interpreter still runs it
        out_dir = self.tmp()
        marker = os.path.join(out_dir, "ran")
        d = self.sibling_repo()
        self.wrapper(os.path.join(d, "bin", "py"), marker)
        self.git(d, "add", "-A")
        self.git(d, "commit", "-qm", "wrapper")
        before = worker.tree_state(d)
        self.write(d, "tests/test_x.py", SIBLING_RED)
        detail = self.unverified(self.teujip(d, before, request=self.ctx(python="bin/py")), "tests/test_x.py")
        self.assertIn("No module named 'support'", detail)
        self.assertTrue(os.path.exists(marker), "the declared interpreter did not run")
        # cwd only: the default interpreter, and red
        d2 = self.sibling_repo()
        before2 = worker.tree_state(d2)
        self.write(d2, "tests/test_x.py", SIBLING_RED)
        self.done(self.teujip(d2, before2, request=self.ctx(cwd="tests")))


class C2Interpreter(Base):

    def setup_repo(self, marker):
        d = self.repo({"tests/support.py": SUPPORT})
        self.wrapper(os.path.join(d, "bin", "py"), marker)
        self.git(d, "add", "-A")
        self.git(d, "commit", "-qm", "wrapper")
        return d

    def test_C2_a_declared_interpreter_relative_to_the_project_is_the_one_that_runs(self):
        marker = os.path.join(self.tmp(), "ran")
        d = self.setup_repo(marker)
        before = worker.tree_state(d)
        self.write(d, "tests/test_x.py", SIBLING_RED)
        self.done(self.teujip(d, before, request=self.ctx(cwd="tests", python="bin/py")))
        self.assertTrue(os.path.exists(marker), "bin/py was not used")

    def test_C2_a_declared_interpreter_by_absolute_path_runs(self):
        marker = os.path.join(self.tmp(), "ran")
        d = self.setup_repo(marker)
        before = worker.tree_state(d)
        self.write(d, "tests/test_x.py", SIBLING_RED)
        self.done(self.teujip(d, before, request=self.ctx(cwd="tests", python=os.path.join(d, "bin", "py"))))
        self.assertTrue(os.path.exists(marker), "the absolute interpreter was not used")

    def test_C2_a_declared_interpreter_in_the_project_file_runs(self):
        marker = os.path.join(self.tmp(), "ran")
        d = self.setup_repo(marker)
        self.write(d, "hacheong/test-context.json", json.dumps({"cwd": "tests", "python": "bin/py"}))
        self.git(d, "add", "-A")
        self.git(d, "commit", "-qm", "ctx")
        before = worker.tree_state(d)
        self.write(d, "tests/test_x.py", SIBLING_RED)
        self.done(self.teujip(d, before))
        self.assertTrue(os.path.exists(marker), "the project's interpreter was not used")

    def test_C2_a_bare_interpreter_name_found_on_path_runs(self):
        out_dir = self.tmp()
        marker = os.path.join(out_dir, "ran")
        bindir = os.path.join(out_dir, "bin")
        self.wrapper(os.path.join(bindir, "hacheong-py-q"), marker)
        d = self.repo({"tests/support.py": SUPPORT})
        before = worker.tree_state(d)
        self.write(d, "tests/test_x.py", SIBLING_RED)
        with mock.patch.dict(os.environ, {"PATH": bindir + os.pathsep + os.environ.get("PATH", "")}):
            out = self.teujip(d, before, request=self.ctx(cwd="tests", python="hacheong-py-q"))
        self.done(out)
        self.assertTrue(os.path.exists(marker), "hacheong-py-q was not used")

    def test_C2_an_interpreter_path_with_whitespace_runs_as_argv0(self):
        # A4: a path to an existing executable may contain whitespace; relative and absolute
        for how in ("relative", "absolute"):
            with self.subTest(how):
                marker = os.path.join(self.tmp(), "ran")
                d = self.repo({"tests/support.py": SUPPORT})
                self.wrapper(os.path.join(d, "bin with spaces", "py"), marker)
                self.git(d, "add", "-A")
                self.git(d, "commit", "-qm", "wrapper")
                before = worker.tree_state(d)
                self.write(d, "tests/test_x.py", SIBLING_RED)
                python = "bin with spaces/py" if how == "relative" else os.path.join(d, "bin with spaces", "py")
                self.done(self.teujip(d, before, request=self.ctx(cwd="tests", python=python)))
                self.assertTrue(os.path.exists(marker), "%r was not run" % python)

    def test_C2_a_name_with_an_argument_or_a_missing_spaced_path_is_still_refused(self):
        d = self.repo({"tests/support.py": SUPPORT})
        self.wrapper(os.path.join(d, "bin with spaces", "py"))
        self.git(d, "add", "-A")
        self.git(d, "commit", "-qm", "wrapper")
        before = worker.tree_state(d)
        self.write(d, "tests/test_x.py", RED_FAIL)
        self.write(d, "tests/test_y.py", RED_FAIL)
        for python in ("python3 -I", "bin with spaces/missing"):
            with self.subTest(python):
                self.broken(d, before, dict(REQUEST, **{"test-context": {"python": python}}))

    def broken(self, d, before, request, paths=("tests/test_x.py", "tests/test_y.py")):
        out = self.teujip(d, before, ans=self.answer(tests=paths), request=request)
        for p in paths:
            self.assertNamesContext(self.unverified(out, p))

    def test_C2_each_broken_request_declaration_is_not_verified_red_with_no_fallback(self):
        outside = self.tmp()
        d = self.repo({"tests/support.py": SUPPORT})
        os.symlink(outside, os.path.join(d, "out"))
        self.write(d, "notes.txt", "x\n")
        self.git(d, "add", "-A")
        self.git(d, "commit", "-qm", "fixtures")
        before = worker.tree_state(d)
        # plain red files: the default context would call them red, so a fallback would pass
        self.write(d, "tests/test_x.py", RED_FAIL)
        self.write(d, "tests/test_y.py", RED_FAIL)
        cases = {
            "unknown key": {"cwd": "tests", "env": "x"},
            "cwd not a string": {"cwd": 1},
            "python not a string": {"python": ["python3"]},
            "absolute cwd": {"cwd": os.path.join(d, "tests")},
            "escaping cwd": {"cwd": ".."},
            "escaping through tests": {"cwd": "tests/../.."},
            "escaping by symlink": {"cwd": "out"},
            "missing cwd": {"cwd": "nowhere"},
            "cwd a file": {"cwd": "notes.txt"},
            "interpreter not found": {"python": "no-such-python-q"},
            "interpreter with an argument": {"python": "python3 -I"},
            "interpreter path missing": {"python": "bin/missing"},
            "interpreter path not executable": {"python": "./notes.txt"},
        }
        for name, decl in cases.items():
            with self.subTest(name):
                self.broken(d, before, dict(REQUEST, **{"test-context": decl}))
        for name, decl in {"a string": "tests", "a list": ["tests"], "a number": 1}.items():
            with self.subTest("test-context " + name):
                self.broken(d, before, dict(REQUEST, **{"test-context": decl}))

    def test_C2_a_broken_project_file_is_not_verified_red_with_no_fallback(self):
        for name, text in {"not JSON": "{cwd: tests", "a list": "[\"tests\"]", "a string": "\"tests\"",
                           "unknown key": json.dumps({"cwd": "tests", "timeout": "1"}), "missing cwd": json.dumps({"cwd": "nowhere"}),
                           "cwd not a string": json.dumps({"cwd": 1})}.items():
            with self.subTest(name):
                d = self.repo({"tests/support.py": SUPPORT, "hacheong/test-context.json": text})
                before = worker.tree_state(d)
                self.write(d, "tests/test_x.py", RED_FAIL)
                self.write(d, "tests/test_y.py", RED_FAIL)
                self.broken(d, before, dict(REQUEST))


class C3Running(Base):

    def test_C3_the_contexts_cwd_is_the_working_directory(self):
        d = self.repo()
        before = worker.tree_state(d)
        self.write(d, "tests/test_x.py", "import os, unittest\nclass T(unittest.TestCase):\n    def test_Q_add(self):\n"
                   "        self.assertNotEqual(os.path.realpath(os.getcwd()), %r)\n" % os.path.realpath(os.path.join(d, "tests")))
        self.done(self.teujip(d, before, request=self.ctx(cwd="tests")))

    def test_C3_loaded_as_python_m_unittest_from_the_cwd(self):
        # under `cd tests && python -m unittest test_x.py` the module is test_x and tests/ is the first import directory
        d = self.repo()
        before = worker.tree_state(d)
        self.write(d, "tests/test_x.py", "import os, sys, unittest\nclass T(unittest.TestCase):\n    def test_Q_add(self):\n"
                   "        self.assertNotEqual((__name__, os.path.realpath(sys.path[0] or os.getcwd())), ('test_x', %r))\n"
                   % os.path.realpath(os.path.join(d, "tests")))
        self.done(self.teujip(d, before, request=self.ctx(cwd="tests")))

    def test_C3_a_file_outside_the_contexts_cwd_is_not_verified_red(self):
        d = self.repo({"tests/support.py": SUPPORT})
        before = worker.tree_state(d)
        self.write(d, "tests/test_x.py", SIBLING_RED)
        self.write(d, "test_root.py", RED_FAIL)
        self.write(d, "other/test_o.py", RED_FAIL)
        out = self.teujip(d, before, ans=self.answer(tests=["tests/test_x.py", "test_root.py", "other/test_o.py"]),
                          request=self.ctx(cwd="tests"))
        for p in ("test_root.py", "other/test_o.py"):
            detail = self.unverified(out, p)
            self.assertIn("outside", detail)
            self.assertIn("cwd", detail)
        self.assertFalse(any(n.startswith("red-before-build: tests/test_x.py") for n in self.notes(out)), out)

    def test_C3_errors_under_a_context_are_still_not_red(self):
        d = self.repo({"tests/support.py": SUPPORT})
        before = worker.tree_state(d)
        files = {
            "tests/test_setup.py": "import unittest\nfrom support import VALUE\nclass T(unittest.TestCase):\n"
                                   "    def setUp(self):\n        raise RuntimeError('setup broke q')\n"
                                   "    def test_Q_add(self):\n        self.fail('x')\n",
            "tests/test_import.py": "import unittest\nfrom support import VALUE\nimport app_not_built_q\nclass T(unittest.TestCase):\n"
                                    "    def test_Q_add(self):\n        self.fail('x')\n",
            "tests/test_runtime.py": "import unittest\nfrom support import VALUE\nclass T(unittest.TestCase):\n"
                                     "    def test_Q_add(self):\n        self.fail('x')\n    def test_Q_more(self):\n        VALUE / 0\n",
            "tests/test_syntax.py": "import unittest\nfrom support import VALUE\nclass T(unittest.TestCase):\n"
                                    "    def test_Q_add(self):\n        self.fail('x'\n",
        }
        for rel, text in files.items():
            self.write(d, rel, text)
        out = self.teujip(d, before, ans=self.answer(tests=list(files)), request=self.ctx(cwd="tests"))
        want = {"tests/test_setup.py": "RuntimeError: setup broke q",
                "tests/test_import.py": "ModuleNotFoundError: No module named 'app_not_built_q'",
                "tests/test_runtime.py": "ZeroDivisionError: division by zero",
                "tests/test_syntax.py": "SyntaxError"}
        for rel, quote in want.items():
            with self.subTest(rel):
                detail = self.unverified(out, rel)
                self.assertIn(quote, detail)
                self.assertNotIn("No module named 'support'", detail)

    def test_C3_the_interpreters_own_output_and_exit_are_not_the_verdict(self):
        d = self.repo()
        self.wrapper(os.path.join(d, "bin", "fake"), body="echo 'FAIL: test_Q_add (test_x.T)'\necho 'AssertionError: not built'\n"
                     "echo 'FAILED (failures=1)' >&2\nexit 1\n")
        self.git(d, "add", "-A")
        self.git(d, "commit", "-qm", "fake")
        before = worker.tree_state(d)
        self.write(d, "tests/test_x.py", GREEN)
        out = self.teujip(d, before, request=self.ctx(cwd="tests", python="bin/fake"))
        self.unverified(out, "tests/test_x.py")


class C4NoInference(Base):

    def test_C4_no_context_is_inferred_from_a_tests_path(self):
        d = self.repo({"tests/support.py": SUPPORT, "tests/run.py": "import subprocess\n"})
        before = worker.tree_state(d)
        self.write(d, "tests/test_x.py", SIBLING_RED)
        detail = self.unverified(self.teujip(d, before), "tests/test_x.py")
        self.assertIn("ModuleNotFoundError: No module named 'support'", detail)


class C5ErrorDetail(Base):

    def test_C5_the_missing_sibling_is_quoted_with_the_root_context(self):
        d = self.repo({"tests/support.py": SUPPORT})
        before = worker.tree_state(d)
        self.write(d, "tests/test_x.py", SIBLING_RED)
        detail = self.unverified(self.teujip(d, before), "tests/test_x.py")
        self.assertIn("ModuleNotFoundError: No module named 'support'", detail)
        self.assertIn(".", detail)
        self.assertIn("python", detail)

    def test_C5_the_context_named_is_the_declared_one(self):
        marker = os.path.join(self.tmp(), "ran")
        d = self.repo({"tests/support.py": SUPPORT})
        self.wrapper(os.path.join(d, "bin", "py"), marker)
        self.git(d, "add", "-A")
        self.git(d, "commit", "-qm", "wrapper")
        before = worker.tree_state(d)
        self.write(d, "tests/test_x.py", "import unittest\nfrom support import VALUE\nclass T(unittest.TestCase):\n"
                   "    def setUp(self):\n        raise KeyError('setup q')\n    def test_Q_add(self):\n        self.fail('x')\n")
        detail = self.unverified(self.teujip(d, before, request=self.ctx(cwd="tests", python="bin/py")), "tests/test_x.py")
        self.assertIn("KeyError: 'setup q'", detail)
        self.assertIn("tests", detail)
        self.assertIn("bin/py", detail)

    def test_C5_the_quoted_line_is_cut_to_200_characters(self):
        d = self.repo()
        before = worker.tree_state(d)
        long = "q" * 400
        self.write(d, "tests/test_x.py", HEAD + "class T(unittest.TestCase):\n    def test_Q_add(self):\n"
                   "        raise RuntimeError(%r)\n" % long)
        detail = self.unverified(self.teujip(d, before), "tests/test_x.py")
        self.assertIn("RuntimeError: " + "q" * 150, detail)
        self.assertNotIn("q" * 201, detail)

    def test_C5_red_and_green_messages_are_unchanged(self):
        d = self.repo({"tests/support.py": SUPPORT})
        before = worker.tree_state(d)
        self.write(d, "tests/test_x.py", "import unittest\nfrom support import VALUE\nclass T(unittest.TestCase):\n"
                   "    def test_Q_add(self):\n        self.assertEqual(VALUE, 1)\n")
        out = self.teujip(d, before, request=self.ctx(cwd="tests"))
        self.failed(out, "red-before-build")
        self.assertIn("red-before-build: tests/test_x.py passes before the build — it decides nothing", self.notes(out), out)


class C6ChangedContext(Base):

    def test_C6_a_project_file_created_during_the_call_is_not_used(self):
        d = self.repo({"tests/support.py": SUPPORT})
        before = worker.tree_state(d)
        self.write(d, "hacheong/test-context.json", json.dumps({"cwd": "tests"}))
        self.write(d, "tests/test_x.py", SIBLING_RED)
        self.write(d, "tests/test_y.py", RED_FAIL)
        out = self.teujip(d, before, ans=self.answer(tests=["tests/test_x.py", "tests/test_y.py"]))
        for p in ("tests/test_x.py", "tests/test_y.py"):
            self.assertIn("changed during this call", self.unverified(out, p))

    def test_C6_a_project_file_edited_or_removed_during_the_call_is_not_used(self):
        for change in ("edit", "remove"):
            with self.subTest(change):
                d = self.repo({"tests/support.py": SUPPORT, "hacheong/test-context.json": json.dumps({"cwd": "tests"})})
                before = worker.tree_state(d)
                if change == "edit":
                    self.write(d, "hacheong/test-context.json", json.dumps({"cwd": "tests", "python": "python3"}))
                else:
                    os.remove(os.path.join(d, "hacheong", "test-context.json"))
                self.write(d, "tests/test_x.py", RED_FAIL)
                self.assertIn("changed during this call", self.unverified(self.teujip(d, before), "tests/test_x.py"))

    def test_C6_without_a_before_snapshot_the_file_is_used_as_it_is(self):
        d = self.tmp()   # no git
        self.write(d, "tests/support.py", SUPPORT)
        self.write(d, "hacheong/test-context.json", json.dumps({"cwd": "tests"}))
        self.write(d, "tests/test_x.py", SIBLING_RED)
        out = self.teujip(d, None)
        self.assertFalse(any(n.startswith("red-before-build") for n in self.notes(out)), out)
        self.assertNotIn("red-before-build", out.get("validation", {}).get("failed", []), out)


class C7Harness(Base):

    def test_C7_writes_nothing_but_pycache_passes_no_timeout_or_pass_fds_and_removes_its_scratch(self):
        marker = os.path.join(self.tmp(), "ran")
        d = self.repo({"tests/support.py": SUPPORT})
        wrapper = self.wrapper(os.path.join(d, "bin", "py"), marker)
        self.write(d, "tests/test_x.py", SIBLING_RED)
        self.git(d, "add", "-A")
        self.git(d, "commit", "-qm", "fixtures")
        before = worker.tree_state(d)
        os.utime(os.path.join(d, "tests", "test_x.py"))
        seen = []
        real = subprocess.Popen

        class Recording(real):
            def __init__(self_, *a, **k):
                argv = a[0] if a else k.get("args")
                seen.append((list(argv) if isinstance(argv, (list, tuple)) else [argv], k))
                super().__init__(*a, **k)

        scratch = self.tmp()
        listing = lambda: sorted(os.path.relpath(os.path.join(a, f), d) for a, _, fs in os.walk(d)
                                 if ".git" not in a.split(os.sep) and "__pycache__" not in a.split(os.sep) for f in fs)
        files = listing()
        # Other tools write their own caches in TMPDIR (on macOS git's xcrun shim leaves xcrun_db there); C7 is about
        # the harness's scratch, so what git alone leaves under the same TMPDIR is recorded first and not held against it.
        others = lambda: {n for n in os.listdir(scratch) if n.startswith("xcrun_db")}
        with mock.patch.dict(os.environ, {"TMPDIR": scratch, "TEMP": scratch, "TMP": scratch}):
            for argv in (["git", "status", "--porcelain"], ["git", "ls-files"], ["git", "rev-parse", "HEAD"]):
                subprocess.run(argv, cwd=d, capture_output=True)
        primed = set(os.listdir(scratch))
        with mock.patch("subprocess.Popen", Recording), mock.patch.object(tempfile, "tempdir", scratch), \
                mock.patch.dict(os.environ, {"TMPDIR": scratch, "TEMP": scratch, "TMP": scratch}):
            out = self.teujip(d, before, request=self.ctx(cwd="tests", python="bin/py"))
        self.done(out)
        runs = [k for argv, k in seen if argv and os.path.realpath(str(argv[0])) == os.path.realpath(wrapper)
                or argv and str(argv[0]) == "bin/py"]
        self.assertTrue(runs, "the declared interpreter was not started through subprocess.Popen: %r" % [a for a, _ in seen])
        self.assertEqual([k for k in runs if k.get("timeout") is not None or k.get("pass_fds")], [], runs)
        st = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all", "--ignored"], cwd=d,
                            capture_output=True, text=True).stdout
        self.assertEqual([l for l in st.splitlines() if "__pycache__" not in l], [], st)
        self.assertEqual(listing(), files)
        self.assertEqual(sorted(set(os.listdir(scratch)) - primed - others()), [], "scratch left behind")

    def call_red(self, target, path):
        try:
            res = worker.unittest_red(target, path)
        except Exception as e:
            self.fail("unittest_red raised %s: %s" % (type(e).__name__, e))
        self.assertIsInstance(res, tuple, res)
        self.assertEqual(len(res), 2, res)
        self.assertEqual(res[0], "unverified", res)
        self.assertIsInstance(res[1], str, res)
        self.assertTrue(res[1].strip(), res)
        return res

    def test_C7_unittest_red_never_raises_without_a_default_interpreter(self):
        # A5: shutil.which finds neither python3 nor python
        d = self.repo({"tests/test_x.py": RED_FAIL})
        patches = [mock.patch.object(shutil, "which", return_value=None)]
        if hasattr(worker, "shutil"):
            patches.append(mock.patch.object(worker.shutil, "which", return_value=None))
        if callable(getattr(worker, "which", None)):
            patches.append(mock.patch.object(worker, "which", return_value=None))
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.call_red(d, "tests/test_x.py")

    def test_C7_unittest_red_never_raises_on_a_missing_target(self):
        # A5: a target directory that does not exist
        missing = os.path.join(self.tmp(), "no-such-project")
        self.call_red(missing, "tests/test_x.py")
        afile = self.write(self.tmp(), "plain.txt", "x\n")
        self.call_red(afile, "tests/test_x.py")


# ======================================================================================================================
# Q-support
# ======================================================================================================================

GROUPS = json.dumps({"thread": ["test_thread"]}) + "\n"
WRITE_SUPPORT = "def body():\n    return {}\n"
THREAD = ("import unittest\nfrom write_support import body\nclass T(unittest.TestCase):\n"
          "    def test_Q_add(self):\n        self.assertIn('text', body(), 'not built')\n")
GUIN = ["tests/test_thread.py", "tests/groups.json", "tests/write_support.py"]


class S1Answer(Base):

    def guin(self):
        d = self.repo()
        before = worker.tree_state(d)
        self.write(d, "tests/groups.json", GROUPS)
        self.write(d, "tests/write_support.py", WRITE_SUPPORT)
        self.write(d, "tests/test_thread.py", THREAD)
        return d, before

    def test_S1_guin_sites_shape_with_support_is_done(self):
        d, before = self.guin()
        out = self.teujip(d, before, ans=self.answer(tests=GUIN, support=GUIN[1:]), request=self.ctx(cwd="tests"))
        self.done(out)
        note = self.starting(out, "support (protected with the tests, not red evidence): ")
        self.assertIn("tests/groups.json", note)
        self.assertIn("tests/write_support.py", note)
        self.assertNotIn("tests/test_thread.py", note)

    def test_S1_an_answer_without_support_is_read_as_empty(self):
        d = self.repo()
        before = worker.tree_state(d)
        self.write(d, "tests/test_x.py", RED_FAIL)
        out = self.teujip(d, before, ans=self.answer())
        self.done(out)
        self.assertFalse(any(n.startswith("support (") for n in self.notes(out)), out)
        out = self.teujip(d, before, ans=self.answer(support=[]))
        self.done(out)
        self.assertFalse(any(n.startswith("support (") for n in self.notes(out)), out)

    def test_S1_teujips_schema_lists_support_in_properties_and_required(self):
        with open(os.path.join(PLUGIN, "members", "teujip", "answer.json"), encoding="utf-8") as fh:
            schema = json.load(fh)
        self.assertIn("support", schema.get("properties", {}))
        self.assertIn("support", schema.get("required", []))
        prop = schema["properties"]["support"]
        self.assertEqual(prop.get("type"), "array", prop)
        self.assertEqual(prop.get("items", {}).get("type"), "string", prop)


class S2Runnable(Base):

    def test_S2_the_same_answer_without_support_is_not_verified_red(self):
        d = self.repo()
        before = worker.tree_state(d)
        self.write(d, "tests/groups.json", GROUPS)
        self.write(d, "tests/write_support.py", WRITE_SUPPORT)
        self.write(d, "tests/test_thread.py", THREAD)
        out = self.teujip(d, before, ans=self.answer(tests=GUIN), request=self.ctx(cwd="tests"))
        self.unverified(out, "tests/groups.json")
        self.unverified(out, "tests/write_support.py")
        self.assertFalse(any(n.startswith("red-before-build: tests/test_thread.py") for n in self.notes(out)), out)

    def test_S2_deleted_and_retired_support_is_skipped(self):
        d = self.repo({"tests/old_support.py": "X = 1\n"})
        before = worker.tree_state(d)
        os.remove(os.path.join(d, "tests", "old_support.py"))
        self.write(d, "tests/test_x.py", RED_FAIL)
        tests = ["tests/test_x.py", "tests/old_support.py", "tests/gone.json"]
        out = self.teujip(d, before, ans=self.answer(tests=tests, support=tests[1:]),
                          request=dict(REQUEST, **{"deleted-tests": ["tests/gone.json"]}))
        self.done(out)


class S3NotADisguisedTest(Base):

    def test_S3_support_named_test_py_is_refused(self):
        d = self.repo()
        before = worker.tree_state(d)
        self.write(d, "tests/test_x.py", RED_FAIL)
        self.write(d, "tests/test_helpers.py", "def helper():\n    return 1\n")
        out = self.teujip(d, before, ans=self.answer(tests=["tests/test_x.py", "tests/test_helpers.py"], support=["tests/test_helpers.py"]))
        self.failed(out, "red-before-build")
        note = self.starting(out, "red-before-build: tests/test_helpers.py is declared support")
        self.assertIn("test module", note)

    def test_S3_support_holding_tests_is_refused_with_their_number(self):
        d = self.repo()
        before = worker.tree_state(d)
        self.write(d, "tests/test_x.py", RED_FAIL)
        self.write(d, "tests/helpers.py", HEAD + "class Hidden(unittest.TestCase):\n    def test_a(self):\n        pass\n"
                   "    def test_b(self):\n        pass\n")
        out = self.teujip(d, before, ans=self.answer(tests=["tests/test_x.py", "tests/helpers.py"], support=["tests/helpers.py"]))
        self.failed(out, "red-before-build")
        note = self.starting(out, "red-before-build: tests/helpers.py is declared support")
        self.assertIn("2", note[len("red-before-build: tests/helpers.py is declared support"):])

    def test_S3_support_loaded_in_the_test_context(self):
        # helpers.py imports its sibling: loadable only from tests/, and there it holds a test
        d = self.repo({"tests/support.py": SUPPORT})
        before = worker.tree_state(d)
        self.write(d, "tests/test_x.py", SIBLING_RED)
        self.write(d, "tests/helpers.py", "import unittest\nfrom support import VALUE\nclass Hidden(unittest.TestCase):\n"
                   "    def test_a(self):\n        pass\n")
        out = self.teujip(d, before, ans=self.answer(tests=["tests/test_x.py", "tests/helpers.py"], support=["tests/helpers.py"]),
                          request=self.ctx(cwd="tests"))
        self.failed(out, "red-before-build")
        self.starting(out, "red-before-build: tests/helpers.py is declared support")

    def test_S3_an_unloadable_support_module_is_a_non_claim_not_a_failure(self):
        d = self.repo()
        before = worker.tree_state(d)
        self.write(d, "tests/test_x.py", RED_FAIL)
        self.write(d, "tests/broken_support.py", "import nowhere_support_q\n")
        out = self.teujip(d, before, ans=self.answer(tests=["tests/test_x.py", "tests/broken_support.py"],
                                                     support=["tests/broken_support.py"]))
        self.done(out)
        hits = [n for n in self.notes(out) if "tests/broken_support.py" in n and "could not be loaded" in n]
        self.assertTrue(hits, out)
        self.assertIn("nowhere_support_q", hits[0])

    def test_S3_a_missing_support_path_does_not_exist(self):
        d = self.repo()
        before = worker.tree_state(d)
        self.write(d, "tests/test_x.py", RED_FAIL)
        out = self.teujip(d, before, ans=self.answer(tests=["tests/test_x.py", "tests/nowhere.json"], support=["tests/nowhere.json"]))
        self.failed(out, "red-before-build")
        self.assertIn("red-before-build: tests/nowhere.json does not exist", self.notes(out), out)
        self.assertFalse(any(n.startswith("red-before-build: tests/nowhere.json is not verified red") for n in self.notes(out)), out)


class S4NoRunnable(Base):

    def test_S4_all_support_is_no_runnable_test(self):
        d = self.repo()
        before = worker.tree_state(d)
        self.write(d, "tests/helpers.py", "X = 1\n")
        self.write(d, "tests/groups.json", GROUPS)
        out = self.teujip(d, before, ans=self.answer(tests=["tests/helpers.py", "tests/groups.json"],
                                                     support=["tests/helpers.py", "tests/groups.json"]))
        self.failed(out, "red-before-build")
        self.starting(out, "red-before-build: no runnable test")


class S5NotPython(Base):

    def test_S5_a_json_listed_only_in_tests_says_it_belongs_in_support(self):
        d = self.repo()
        before = worker.tree_state(d)
        self.write(d, "tests/test_x.py", RED_FAIL)
        self.write(d, "tests/groups.json", GROUPS)
        out = self.teujip(d, before, ans=self.answer(tests=["tests/test_x.py", "tests/groups.json"]))
        detail = self.unverified(out, "tests/groups.json")
        self.assertIn("support", detail)


class S6Allowed(Base):

    def test_S6_support_outside_tests_is_allowed_by_only_tests_touched(self):
        d = self.repo()
        before = worker.tree_state(d)
        self.write(d, "tests/test_x.py", RED_FAIL)
        self.write(d, "fixtures/data.json", "{}\n")
        out = self.teujip(d, before, ans=self.answer(tests=["tests/test_x.py", "fixtures/data.json"], support=["fixtures/data.json"]))
        self.done(out)
        self.assertNotIn("only-tests-touched", out.get("validation", {}).get("failed", []), out)

    def test_S6_support_missing_from_tests_is_a_stray_never_allowed(self):
        # A1: only-tests-touched allows `tests` and tests/ or test/ — never `support`
        d = self.repo()
        before = worker.tree_state(d)
        self.write(d, "tests/test_x.py", RED_FAIL)
        self.write(d, "fixtures/data.json", "{}\n")
        st = claude_stream(("Write", {"file_path": d + "/tests/test_x.py"}), ("Write", {"file_path": d + "/fixtures/data.json"}))
        out = self.teujip(d, before, ans=self.answer(tests=["tests/test_x.py"], support=["fixtures/data.json"]), stream_text=st)
        self.failed(out, "only-tests-touched")
        self.assertIn(WROTE + "fixtures/data.json", self.notes(out), json.dumps(out, indent=1))


class S9WellFormed(Base):

    def support_problem(self, out, path=None):
        self.failed(out, "red-before-build")
        hits = [n for n in self.notes(out) if n.startswith("red-before-build: support ")]
        self.assertTrue(hits, json.dumps(out, indent=1))
        if path is not None:
            named = [n for n in hits if path in n or json.dumps(path) in n or repr(path) in n]
            self.assertTrue(named, "no support problem names %r:\n%s" % (path, json.dumps(out, indent=1)))
            return named[0]
        return hits[0]

    def test_S9_support_outside_tests_dir_not_in_tests_fails_both_gates(self):
        d = self.repo()
        before = worker.tree_state(d)
        self.write(d, "tests/test_x.py", RED_FAIL)
        self.write(d, "fixtures/data.json", "{}\n")
        st = claude_stream(("Write", {"file_path": d + "/tests/test_x.py"}), ("Write", {"file_path": d + "/fixtures/data.json"}))
        out = self.teujip(d, before, ans=self.answer(tests=["tests/test_x.py"], support=["fixtures/data.json"]), stream_text=st)
        note = self.support_problem(out, "fixtures/data.json")
        self.assertIn("not in", note)
        self.assertIn("tests", note)
        self.failed(out, "only-tests-touched")
        self.assertIn(WROTE + "fixtures/data.json", self.notes(out), json.dumps(out, indent=1))

    def test_S9_support_groups_json_not_in_tests_fails(self):
        d = self.repo()
        before = worker.tree_state(d)
        self.write(d, "tests/test_x.py", RED_FAIL)
        self.write(d, "tests/groups.json", GROUPS)
        st = claude_stream(("Write", {"file_path": d + "/tests/test_x.py"}), ("Write", {"file_path": d + "/tests/groups.json"}))
        out = self.teujip(d, before, ans=self.answer(tests=["tests/test_x.py"], support=["tests/groups.json"]), stream_text=st)
        note = self.support_problem(out, "tests/groups.json")
        self.assertIn("not in", note)

    def test_S9_absent_or_null_support_is_empty(self):
        d = self.repo()
        before = worker.tree_state(d)
        self.write(d, "tests/test_x.py", RED_FAIL)
        ans = self.answer()
        ans["support"] = None
        out = self.teujip(d, before, ans=ans)
        self.done(out)
        self.assertFalse(any(n.startswith("red-before-build: support ") or n.startswith("support (") for n in self.notes(out)), out)

    def test_S9_malformed_support_values_fail_without_an_exception(self):
        for name, value in {"a string": "tests/helpers.py", "an object": {"tests/helpers.py": True}, "a number": 1,
                            "[1]": [1], "[null]": [None], "a list inside": [["tests/helpers.py"]]}.items():
            with self.subTest(name):
                d = self.repo()
                before = worker.tree_state(d)
                self.write(d, "tests/test_x.py", RED_FAIL)
                self.write(d, "tests/helpers.py", "X = 1\n")
                ans = self.answer(tests=["tests/test_x.py", "tests/helpers.py"])
                ans["support"] = value
                self.support_problem(self.teujip(d, before, ans=ans))

    def test_S9_unsafe_support_paths_fail_without_an_exception(self):
        for p in ("/abs/x.json", "../x.json", "tests/../../x.json", "", "tests\\x.json", "tests/x\x00.json"):
            with self.subTest(p):
                d = self.repo()
                before = worker.tree_state(d)
                self.write(d, "tests/test_x.py", RED_FAIL)
                # listed in tests too: the refusal must be for the path itself, not for a missing `tests` entry
                out = self.teujip(d, before, ans=self.answer(tests=["tests/test_x.py", p], support=[p]))
                self.support_problem(out, p or None)

    def test_S9_a_support_symlink_resolving_outside_the_project_fails(self):
        outside = self.tmp()
        self.write(outside, "x.json", "{}\n")
        d = self.repo()
        os.symlink(outside, os.path.join(d, "out"))
        self.git(d, "add", "-A")
        self.git(d, "commit", "-qm", "link")
        before = worker.tree_state(d)
        self.write(d, "tests/test_x.py", RED_FAIL)
        out = self.teujip(d, before, ans=self.answer(tests=["tests/test_x.py", "out/x.json"], support=["out/x.json"]))
        self.support_problem(out, "out/x.json")


class S9RegularFiles(Base):
    """A7: a support entry must resolve to an existing regular file inside the project."""

    support_problem = S9WellFormed.support_problem

    def not_a_file(self, out, entry, named="tests/fixtures"):
        self.assertNotEqual(out["status"], "done", json.dumps(out, indent=1))
        note = self.support_problem(out, named)
        self.assertIn("regular file", note)
        for n in self.notes(out):
            if n.startswith("support (protected with the tests, not red evidence): "):
                self.assertNotIn(named, n, json.dumps(out, indent=1))

    def fixtures_repo(self):
        d = self.repo({"tests/fixtures/data.json": "{}\n"})
        before = worker.tree_state(d)
        self.write(d, "tests/test_x.py", RED_FAIL)
        return d, before

    def test_S9_a_committed_directory_as_support_is_refused(self):
        d, before = self.fixtures_repo()
        e = "tests/fixtures"
        out = self.teujip(d, before, ans=self.answer(tests=["tests/test_x.py", e], support=[e]))
        self.not_a_file(out, e)

    def test_S9_a_directory_with_a_trailing_slash_as_support_is_refused(self):
        d, before = self.fixtures_repo()
        e = "tests/fixtures/"
        out = self.teujip(d, before, ans=self.answer(tests=["tests/test_x.py", e], support=[e]))
        self.not_a_file(out, e)

    def test_S9_a_symlink_to_a_directory_as_support_is_refused(self):
        d = self.repo({"tests/fixtures/data.json": "{}\n"})
        os.symlink("fixtures", os.path.join(d, "tests", "fixlink"))
        self.git(d, "add", "-A")
        self.git(d, "commit", "-qm", "link")
        before = worker.tree_state(d)
        self.write(d, "tests/test_x.py", RED_FAIL)
        e = "tests/fixlink"
        out = self.teujip(d, before, ans=self.answer(tests=["tests/test_x.py", e], support=[e]))
        self.not_a_file(out, e, named="tests/fixlink")

    def test_S9_a_regular_support_file_is_still_done(self):
        d, before = self.fixtures_repo()
        e = "tests/fixtures/data.json"
        out = self.teujip(d, before, ans=self.answer(tests=["tests/test_x.py", e], support=[e]))
        self.done(out)
        note = self.starting(out, "support (protected with the tests, not red evidence): ")
        self.assertIn(e, note)
        self.assertFalse(any(n.startswith("red-before-build: support ") for n in self.notes(out)), out)

    def test_S9_a_support_file_deleted_by_the_writer_is_still_skipped(self):
        d, before = self.fixtures_repo()
        os.remove(os.path.join(d, "tests", "fixtures", "data.json"))
        e = "tests/fixtures/data.json"
        out = self.teujip(d, before, ans=self.answer(tests=["tests/test_x.py", e], support=[e]))
        self.done(out)
        self.assertFalse(any(n.startswith("red-before-build: support ") or n.startswith("red-before-build: %s" % e)
                             for n in self.notes(out)), out)


class S7BuilderProtected(Base):

    def test_S7_tests_kept_refuses_a_build_that_changed_or_removed_support(self):
        for victim, change in (("tests/groups.json", "edit"), ("tests/write_support.py", "edit"),
                               ("tests/groups.json", "remove"), ("tests/write_support.py", "remove")):
            with self.subTest(victim=victim, change=change):
                d = self.repo({"tests/test_x.py": RED_FAIL, "tests/groups.json": GROUPS, "tests/write_support.py": WRITE_SUPPORT})
                request = dict(BUILD_REQUEST, tests=["tests/test_x.py", "tests/groups.json", "tests/write_support.py"])
                ran = claude_stream(("Bash", {"command": "python3 -m unittest tests/test_x.py -k Q_add"}))
                before = worker.tree_state(d)
                self.write(d, "app.py", "x = 1\n")
                dakdol = worker.load_member("dakdol")
                ok = worker.validate(json.loads(json.dumps(GOOD_BUILD)), dakdol, request, d, ran, "claude-code", before)
                self.assertEqual(ok["status"], "done", ok)
                if change == "edit":
                    self.write(d, victim, "# changed by the builder\n")
                else:
                    os.remove(os.path.join(d, victim))
                out = worker.validate(json.loads(json.dumps(GOOD_BUILD)), dakdol, request, d, ran, "claude-code", before)
                self.assertEqual(out["status"], "failed", out)
                self.assertIn("tests-kept", out["validation"]["failed"], out)
                self.assertIn(victim, " ".join(out["non-claims"]), out)


class S8Amending(Base):

    def test_S8_amending_skips_support_checks(self):
        d = self.repo()
        before = worker.tree_state(d)
        self.write(d, "tests/test_x.py", GREEN)
        self.write(d, "tests/test_helpers.py", "X = 1\n")
        amend = dict(REQUEST, amending=[{"test": "tests/test_x.py", "contract_quote": "x", "why": "y"}])
        out = self.teujip(d, before, ans=self.answer(tests=["tests/test_x.py", "tests/test_helpers.py"], support=["tests/test_helpers.py"]),
                          request=amend)
        self.done(out)
        self.assertFalse(any(n.startswith("red-before-build") for n in self.notes(out)), out)


# ======================================================================================================================
# Q-touch
# ======================================================================================================================

P = "src/app.py"


class Touch(Base):

    def stray_repo(self, strays=(P,)):
        d = self.repo({s: "original\n" for s in strays})
        before = worker.tree_state(d)
        self.write(d, "tests/test_x.py", RED_FAIL)
        for s in strays:
            self.write(d, s, "changed by another hand\n")
        return d, before

    def own(self, d):
        return ("Write", {"file_path": d + "/tests/test_x.py"})

    def no_read(self, out, path=P):
        """A3/A2: never the read non-claim for `path`."""
        self.assertFalse(any(("only read" in n or "ownership" in n) and path in n for n in self.notes(out)),
                         "given the read non-claim:\n" + json.dumps(out, indent=1))

    def wrote(self, out, path=P):
        self.failed(out, "only-tests-touched")
        self.assertIn(WROTE + path, self.notes(out), json.dumps(out, indent=1))
        self.assertFalse(any("could have written" in n for n in self.notes(out)), out)
        self.no_read(out, path)

    def unclear(self, out, path=P):
        self.failed(out, "only-tests-touched")
        self.assertNotIn(WROTE + path, self.notes(out), "unclear given 2.0.1's wrote wording:\n" + json.dumps(out, indent=1))
        hits = [n for n in self.notes(out) if n.startswith("only-tests-touched: ") and path in n and "could have written" in n]
        self.assertTrue(hits, json.dumps(out, indent=1))
        self.no_read(out, path)
        return hits[0]

    def read_notes(self, out):
        return [n for n in self.notes(out) if "only read evidence" in n and "ownership" in n]

    def read(self, out, paths=(P,)):
        """A3: read is evidence, not ownership — never 'by another hand'."""
        self.done(out)
        hits = self.read_notes(out)
        self.assertTrue(hits, json.dumps(out, indent=1))
        for p in paths:
            self.assertIn(p, hits[0])
        self.assertNotIn("by another hand", hits[0])
        self.assertFalse(any("by another hand" in n and "only read" in n for n in self.notes(out)), out)
        return hits[0]

    def bash(self, d, before, *commands):
        st = claude_stream(self.own(d), *[("Bash", {"command": c}) for c in commands], result=self.answer())
        return self.teujip(d, before, stream_text=st)


class T1Classes(Touch):

    def test_T1_guin_sites_thread_write_tests_replay_is_done(self):
        body, plan, other = "lexicons/com/x/body.json", "plan/ATPROTO.md", "src/other.ts"
        d, before = self.stray_repo((body, plan, other))
        out = self.bash(d, before, 'cat lexicons/com/x/body.json; grep -n "^## Q-thread" -A80 plan/ATPROTO.md | sed -n 1,200p')
        note = self.read(out, (body, plan))
        self.assertNotIn(other, note)
        self.assertIn(NEVER + other, self.notes(out), out)

    def test_T1_each_write_tool_is_wrote(self):
        for tool in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
            with self.subTest(tool):
                d, before = self.stray_repo()
                st = claude_stream(self.own(d), (tool, {"file_path": d + "/" + P}), result=self.answer())
                self.wrote(self.teujip(d, before, stream_text=st))

    def test_T1_a_codex_file_change_is_wrote(self):
        d, before = self.stray_repo()
        st = codex_stream(("files", [d + "/tests/test_x.py"]), ("files", [d + "/" + P]))
        self.wrote(self.teujip(d, before, stream_text=st, host="codex"))

    def test_T1_each_shell_write_is_wrote(self):
        commands = [
            "echo x > src/app.py", "echo x >> src/app.py", "echo x >| src/app.py", "make &> src/app.py", "make &>> src/app.py",
            "echo x>src/app.py", "echo x | tee src/app.py", "echo x | tee -a src/app.py",
            "sed -i '' 's/a/b/' src/app.py", "sed -i.bak 's/a/b/' src/app.py", "sed -I '' 's/a/b/' src/app.py",
            "sed --in-place 's/a/b/' src/app.py", "perl -i -pe 's/a/b/' src/app.py", "perl -i.bak -pe 's/a/b/' src/app.py",
            "rm src/app.py", "rm -f src/app.py", "unlink src/app.py", "mv src/app.py src/b.py", "mv src/b.py src/app.py",
            "touch src/app.py", "truncate -s 0 src/app.py", "ln -sf other src/app.py", "cp tests/test_x.py src/app.py",
            "git checkout -- src/app.py", "git checkout HEAD src/app.py", "git restore src/app.py", "git restore --staged src/app.py",
            "git rm src/app.py", "git mv src/app.py src/b.py",
        ]
        for c in commands:
            with self.subTest(c):
                d, before = self.stray_repo()
                self.wrote(self.bash(d, before, c))

    def test_T1_unclear_forms_are_not_reads_and_not_wrote(self):
        commands = [
            "python3 - <<'EOF'\nopen('src/app.py', 'w').write('x')\nEOF",
            "python3 -c \"open('src/app.py', 'w').write('x')\"",
            "node -e \"require('fs').writeFileSync('src/app.py', 'x')\"",
            "awk '{print > \"src/app.py\"}' README.md",
            "python3 fix.py src/app.py",
            "echo src/app.py | xargs rm",
            "cat src/app.py | python3 fix.py",
            "cat $(echo src/app.py)",
            "cat `echo src/app.py`",
            "diff <(cat src/app.py) README.md",
            "cat 'src/app.py",
            "F=src/app.py; cat $F",
            "for f in src/app.py; do cat $f; done",
            "cat <<EOF\nsrc/app.py\nEOF",
        ]
        for c in commands:
            with self.subTest(c):
                d, before = self.stray_repo()
                self.unclear(self.bash(d, before, c))

    def test_T1_plain_reads_are_read(self):
        commands = ["cat src/app.py", "head -5 src/app.py", "tail -n 3 src/app.py", "nl src/app.py", "wc -l < src/app.py",
                    "grep -n add src/app.py | sed -n 1,20p", "rg add src/app.py | head -3", "ls -l src/app.py", "stat src/app.py",
                    "file src/app.py", "jq . src/app.py", "diff src/app.py README.md", "cmp src/app.py README.md",
                    "git diff src/app.py", "git log -p -- src/app.py", "git show HEAD:src/app.py", "git blame src/app.py",
                    "sed -n 1,40p src/app.py", "echo src/app.py", "printf '%s' src/app.py", "egrep x src/app.py; fgrep y src/app.py",
                    # A2: simple reads stay read
                    "grep -n x src/app.py", "sed -n 1,200p src/app.py", "sed -n '/^## Q/,/^## /p' src/app.py",
                    "sed 's/x/y/g' src/app.py", "git diff -- src/app.py", "head src/app.py", "tail src/app.py", "wc src/app.py"]
        for c in commands:
            with self.subTest(c):
                d, before = self.stray_repo()
                self.read(self.bash(d, before, c))

    def test_T1_a_reader_with_a_switch_or_script_that_writes_its_path_is_wrote(self):
        # A2: the path shown to be the write target of a reader's switch, redirection or script part
        commands = [
            "echo changed >& src/app.py", "echo changed >>& src/app.py",
            "sed -ni 's/x/y/' src/app.py", "sed -Ei 's/x/y/' src/app.py", "sed -I.bak s/x/y/ src/app.py",
            "sed -i.bak s/x/y/ src/app.py", "sed -nEi 's/x/y/p' src/app.py",
            "sed 's/x/y/w src/app.py' README.md", "sed -n 'w src/app.py' README.md",
            "git diff --output src/app.py", "git diff --output=src/app.py", "git log -p --output src/app.py",
            "git show HEAD --output=src/app.py",
            "less -o src/app.py README.md", "less -O src/app.py README.md",
        ]
        for c in commands:
            with self.subTest(c):
                d, before = self.stray_repo()
                self.wrote(self.bash(d, before, c))

    def test_T1_a_reader_with_a_switch_or_script_that_can_write_or_execute_is_unclear_never_read(self):
        # A2: a reader word with a part that can write, execute or redirect elsewhere — P is not shown to be its target
        commands = [
            "sed -f script.sed src/app.py", "sed --file=script.sed src/app.py",
            "sed 's/x/y/e' src/app.py", "sed '1e echo hi' src/app.py",
            "sed 's/x/y/w out.txt' src/app.py", "sed -n 'w out.txt' src/app.py", "sed '1W out.txt' src/app.py",
            "rg --pre cat x src/app.py", "rg --pre=cat x src/app.py",
            "git diff --output out.txt src/app.py", "git diff --output=out.txt -- src/app.py",
            "git log -p --output=out.txt -- src/app.py",
            "less -o out.txt src/app.py", "less -O out.txt src/app.py",
        ]
        for c in commands:
            with self.subTest(c):
                d, before = self.stray_repo()
                self.unclear(self.bash(d, before, c))

    def test_T1_a_read_tool_is_read(self):
        d, before = self.stray_repo()
        st = claude_stream(self.own(d), ("Read", {"file_path": d + "/" + P}), result=self.answer())
        self.read(self.teujip(d, before, stream_text=st))

    def test_T1_read_plus_write_of_the_same_path_is_wrote(self):
        for cmds in (["cat src/app.py", "echo x > src/app.py"], ["cat src/app.py; echo x > src/app.py"],
                     ["cat src/app.py", "python3 fix.py src/app.py", "rm src/app.py"]):
            with self.subTest(cmds):
                d, before = self.stray_repo()
                self.wrote(self.bash(d, before, *cmds))
        d, before = self.stray_repo()
        st = claude_stream(self.own(d), ("Read", {"file_path": d + "/" + P}), ("Edit", {"file_path": d + "/" + P}), result=self.answer())
        self.wrote(self.teujip(d, before, stream_text=st))

    def test_T1_read_plus_unclear_is_unclear(self):
        d, before = self.stray_repo()
        self.unclear(self.bash(d, before, "cat src/app.py", "python3 fix.py src/app.py"))

    def test_T1_codex_shell_wrappers_are_unwrapped(self):
        for kind, cmd in (("cmd", "cat src/app.py"), ("raw", "bash -lc 'cat src/app.py'"), ("raw", "/bin/zsh -lc \"head -3 src/app.py\"")):
            with self.subTest(cmd):
                d, before = self.stray_repo()
                st = codex_stream(("files", [d + "/tests/test_x.py"]), (kind, cmd))
                self.read(self.teujip(d, before, stream_text=st, host="codex"))
        for kind, cmd in (("cmd", "echo x > src/app.py"), ("raw", "bash -lc 'rm src/app.py'")):
            with self.subTest(cmd):
                d, before = self.stray_repo()
                st = codex_stream(("files", [d + "/tests/test_x.py"]), (kind, cmd))
                self.wrote(self.teujip(d, before, stream_text=st, host="codex"))
        d, before = self.stray_repo()
        st = codex_stream(("files", [d + "/tests/test_x.py"]), ("cmd", "python3 -c \"open('src/app.py','w')\""))
        self.unclear(self.teujip(d, before, stream_text=st, host="codex"))


class T1SedShortOptions(Touch):
    """A6: a sed option word is read as short option letters; `e`/`f` take the rest of the word as their argument."""

    V = "victim.txt"

    def classify(self, command):
        touch = getattr(worker, "shell_touch", None)
        self.assertTrue(callable(touch), "worker.shell_touch is missing")
        return touch(command, self.V)[0]

    def test_T1_sed_e_with_an_attached_script_is_a_read(self):
        c = "sed -es/input/output/g victim.txt"
        self.assertEqual(self.classify(c), "read", c)
        d, before = self.stray_repo((self.V,))
        out = self.bash(d, before, c)
        self.assertNotIn(WROTE + self.V, self.notes(out), "given 2.0.1's wrote problem:\n" + json.dumps(out, indent=1))
        self.read(out, (self.V,))

    def test_T1_sed_f_with_an_attached_script_file_is_unclear(self):
        c = "sed -fprint.sed victim.txt"
        self.assertEqual(self.classify(c), "unclear", c)
        d, before = self.stray_repo((self.V,))
        self.unclear(self.bash(d, before, c), self.V)


class T2Messages(Touch):

    def test_T2_unclear_names_the_paths_and_quotes_a_command_cut_to_120(self):
        d, before = self.stray_repo()
        c = "python3 fix.py src/app.py"
        self.assertIn(c, self.unclear(self.bash(d, before, c)))
        d, before = self.stray_repo()
        long = "python3 fix.py --mode=" + "z" * 200 + " src/app.py"
        note = self.unclear(self.bash(d, before, long))
        self.assertIn(long[:100], note)
        self.assertNotIn("z" * 120, note)

    def test_T2_wrote_paths_are_comma_separated_as_in_2_0_1(self):
        d, before = self.stray_repo(("src/a.py", "src/b.py"))
        out = self.bash(d, before, "rm src/a.py src/b.py", "cat README.md")
        self.failed(out, "only-tests-touched")
        self.assertTrue(any(n.startswith(WROTE) and "src/a.py" in n and "src/b.py" in n and ", " in n for n in self.notes(out)), out)

    def test_T2_wrote_unclear_and_read_paths_are_each_told(self):
        d, before = self.stray_repo(("src/w.py", "src/u.py", "src/r.py", "src/n.py"))
        out = self.bash(d, before, "echo x > src/w.py", "python3 fix.py src/u.py", "cat src/r.py")
        self.failed(out, "only-tests-touched")
        self.assertIn(WROTE + "src/w.py", self.notes(out), out)
        unclear = [n for n in self.notes(out) if n.startswith("only-tests-touched: ") and "could have written" in n]
        self.assertTrue(unclear and "src/u.py" in unclear[0] and "src/w.py" not in unclear[0], out)
        read = self.read_notes(out)
        self.assertTrue(read and "src/r.py" in read[0] and "src/u.py" not in read[0] and "src/w.py" not in read[0], out)
        self.assertNotIn("by another hand", read[0])
        self.assertIn(NEVER + "src/n.py", self.notes(out), out)


class T3NoTranscript(Touch):

    def test_T3_no_transcript_is_strict(self):
        d, before = self.stray_repo()
        self.wrote(self.teujip(d, before, stream_text=""))


class T4NothingRelaxedButRead(Touch):

    def test_T4_a_write_is_never_a_non_claim(self):
        d, before = self.stray_repo(("src/a.py",))
        out = self.bash(d, before, "cat src/a.py", "sed -i '' 's/x/y/' src/a.py", "head src/a.py")
        self.wrote(out, "src/a.py")
        self.assertFalse(any("only read" in n for n in self.notes(out)), out)

    def test_T4_a_path_mentioned_as_a_substring_is_still_named(self):
        # 2.0.1 counted any text containing the path as named; a non-word mention is not shown to be a read
        d, before = self.stray_repo()
        out = self.bash(d, before, "cat xsrc/app.py.bak")
        self.assertFalse(any(n.startswith(NEVER) and P in n for n in self.notes(out)), out)
        self.unclear(out)


class T4A8Review(Touch):
    """A8: inputs from the final independent review that broke T1/T4 (a write is never read; an unprovable mention is
    unclear) and 2.0.1's "no exception". shell_touch is called on text only; nothing under test is executed."""

    V = "victim.txt"

    def classify(self, command):
        touch = getattr(worker, "shell_touch", None)
        self.assertTrue(callable(touch), "worker.shell_touch is missing")
        try:
            return touch(command, self.V)[0]
        except Exception as e:
            self.fail("shell_touch raised %s: %s" % (type(e).__name__, e))

    def never_read_or_done(self, out):
        self.assertNotEqual(out.get("status"), "done", json.dumps(out, indent=1))
        self.no_read(out, self.V)

    def check(self, c, expected):
        """One command; called from a test body's own subTest, so a failure unwinds through the test method."""
        self.assertEqual(self.classify(c), expected, c)
        d, before = self.stray_repo((self.V,))
        out = self.bash(d, before, c)
        if expected == "read":
            self.read(out, (self.V,))
            return
        self.never_read_or_done(out)
        if expected == "wrote":
            self.wrote(out, self.V)
        else:
            self.unclear(out, self.V)

    def test_T4_A8_sed_escaped_backslash_ends_the_address_and_e_executes_unclear(self):
        for c in (r"sed -nE '/^|\\/e touch pwned #/p' victim.txt", r"sed -n '/^\|\\/e touch pwned #/p' victim.txt"):
            with self.subTest(c):
                self.check(c, "unclear")
        # the boundary: a backslash-escaped delimiter stays inside the address, so this one stays read
        with self.subTest("boundary"):
            self.check(r"sed -n '/a\/b/p' victim.txt", "read")

    def test_T4_A8_hash_inside_a_word_is_not_a_comment(self):
        for c in ("cat victim.txt a#; rm victim.txt", "sed -n p victim.txt x#y; sed -i s/a/b/ victim.txt"):
            with self.subTest(c):
                self.check(c, "wrote")

    def test_T4_A8_a_wrapper_followed_by_more_command_is_not_unwrapped(self):
        for c in ("bash -c 'cat victim.txt'; rm victim.txt", "sh -c 'cat victim.txt' && rm victim.txt"):
            with self.subTest(c):
                self.check(c, "wrote")
        # the boundary: a wrapper whose argument is the whole remaining command is still unwrapped
        for c in ('/bin/zsh -lc "cat victim.txt"', "bash -lc 'cat victim.txt'"):
            with self.subTest(c):
                self.check(c, "read")

    def test_T4_A8_a_wrapper_with_a_harmless_suffix_is_unclear_not_wrote(self):
        # not unwrapped, the full command is classified as written: nothing in it writes victim.txt, and the read inside the
        # wrapper's argument cannot be proven a read — unclear, never wrote merely because the argument is not the whole command
        for c in ("bash -c 'cat victim.txt' ignored", "bash -c 'cat victim.txt'; echo hi", "bash -c 'cat victim.txt' 2>&1"):
            with self.subTest(c):
                self.check(c, "unclear")

    def test_T4_A8_read_write_redirection_is_wrote(self):
        for c in ("cat other.txt 1<>victim.txt", "echo hi 1<>victim.txt"):
            with self.subTest(c):
                self.check(c, "wrote")

    def test_T4_A8_tests_not_an_array_fails_red_before_build_without_an_exception(self):
        d = self.repo()
        before = worker.tree_state(d)
        self.write(d, "tests/test_x.py", RED_FAIL)
        ans = self.answer()
        ans["tests"] = "tests/test_x.py"
        out = self.teujip(d, before, ans=ans)
        self.failed(out, "red-before-build")
        self.assertTrue(any(n.startswith("red-before-build") for n in self.notes(out)), json.dumps(out, indent=1))


if __name__ == "__main__":
    unittest.main()
