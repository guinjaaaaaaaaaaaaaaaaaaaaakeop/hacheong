"""Packaging regression tests for hacheong 2.2.0: the installed payload is plugin/, the repository root is for development.

Standard library only. The runtime is never imported into this process: it is reached through fresh interpreters and by
reading files, so this file loads before plugin/ exists. Every check inspects files on disk, never git HEAD or the index.
"""

import ast
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import tokenize
import unittest

ROOT = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.join(ROOT, "plugin")

MEMBERS = ("chojja", "dakdol", "sibi", "teujip")
DOMAINS = ("code", "plan", "refactor", "site")
ROLE_OF = {"build": "dakdol", "quibble": "sibi", "nitpick": "teujip", "newbie": "chojja"}
SUITES = ("test_hacheong.py", "test_native_prompt.py", "test_hostcall_env.py", "test_record_paths.py",
          "test_red_gate.py", "test_tests_writer.py")

P1_FILES = {"README.md", "LICENSE", "hacheong.py", "worker.py", "hostcall.py", "plugin.json",
            ".claude-plugin/plugin.json", ".codex-plugin/plugin.json", "skills/hire/SKILL.md"}
P1_FILES |= {"members/%s/%s" % (m, f) for m in MEMBERS for f in ("ROLE.md", "answer.json", "policy.json")}
P1_FILES |= {"domains/%s/DOMAIN.md" % d for d in DOMAINS}

FAKE_RESULT = {"type": "result", "subtype": "success", "is_error": False, "num_turns": 1, "total_cost_usd": 0,
               "session_id": "fake", "structured_output": {"status": "done", "summary": "nothing open", "findings": [],
                                                           "non-claims": [], "lacked": []}}

FAKE_CLAUDE = r'''#!%s
import json, os, sys
here = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(here, "stdin.txt"), "w", encoding="utf-8") as f:
    f.write(sys.stdin.read())
with open(os.path.join(here, "env.json"), "w", encoding="utf-8") as f:
    json.dump({"AGENT_WORKER": os.environ.get("AGENT_WORKER"), "AGENT_HOST": os.environ.get("AGENT_HOST")}, f)
print(%r)
'''

LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")


def request(target, role="quibble", **more):
    req = {"artifact-type": "chongdae/request@1", "stage": "build", "run": "run-1", "task": "T1", "role": role,
           "target": target, "goal": "g", "brief": "make it", "closes": [], "contract": {}, "checks": [],
           "domain": "code", "response": "./r.json"}
    req.update(more)
    return req


def clean_env(**more):
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTHON")}
    env.update(more)
    return env


def relative_links(path):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    out = []
    for target in LINK.findall(text):
        if target.startswith(("http:", "https:", "mailto:", "#")):
            continue
        out.append(target.split("#", 1)[0])
    return out


def inside(path, root):
    path, root = os.path.realpath(path), os.path.realpath(root)
    return os.path.commonpath([path, root]) == root


class Base(unittest.TestCase):

    def tmp(self):
        d = tempfile.mkdtemp(prefix="hacheong-packaging-")
        self.addCleanup(shutil.rmtree, d, True)
        self.assertFalse(inside(d, ROOT), "temporary directory %s is inside the repository" % d)
        return d

    def repo(self):
        d = self.tmp()
        git = lambda *a: subprocess.run(["git", *a], cwd=d, capture_output=True, text=True, env=clean_env())
        self.assertEqual(git("init", "-q").returncode, 0)
        with open(os.path.join(d, "README"), "w") as f:
            f.write("a target\n")
        git("config", "user.email", "test@example.invalid")
        git("config", "user.name", "test")
        git("add", "README")
        done = git("commit", "-q", "-m", "init")
        self.assertEqual(done.returncode, 0, done.stderr)
        return d

    def write_json(self, d, name, obj):
        p = os.path.join(d, name)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(obj, f)
        return p

    def run_py(self, *argv, cwd, env=None):
        return subprocess.run([sys.executable, *argv], cwd=cwd, capture_output=True, env=env or clean_env())

    def need_plugin(self):
        self.assertTrue(os.path.isdir(PLUGIN), "the payload plugin/ does not exist")

    def read_json(self, *parts):
        p = os.path.join(*parts)
        self.assertTrue(os.path.isfile(p), "%s is missing" % p)
        with open(p, encoding="utf-8") as f:
            return json.load(f)


def payload_entries():
    files, dirs, links = set(), set(), []
    for top, dnames, fnames in os.walk(PLUGIN):
        for n in list(dnames):
            p = os.path.join(top, n)
            if os.path.islink(p):
                links.append(os.path.relpath(p, PLUGIN))
            if n == "__pycache__":
                dnames.remove(n)
                continue
            dirs.add(os.path.relpath(p, PLUGIN).replace(os.sep, "/"))
        for n in fnames:
            p = os.path.join(top, n)
            if os.path.islink(p):
                links.append(os.path.relpath(p, PLUGIN))
            files.add(os.path.relpath(p, PLUGIN).replace(os.sep, "/"))
    return files, dirs, links


class P_Payload(Base):

    def test_P1_payload_holds_exactly_the_listed_files(self):
        self.need_plugin()
        files, dirs, _ = payload_entries()
        self.assertEqual(sorted(files - P1_FILES), [], "files under plugin/ that P1 does not list")
        self.assertEqual(sorted(P1_FILES - files), [], "files P1 lists that plugin/ lacks")
        wanted_dirs = {"/".join(f.split("/")[:i]) for f in P1_FILES for i in range(1, f.count("/") + 1)}
        self.assertEqual(sorted(dirs - wanted_dirs), [], "directories under plugin/ holding nothing P1 lists")

    def test_P1_no_development_material_anywhere_in_payload(self):
        self.need_plugin()
        banned_files = {"AGENTS.md", "CLAUDE.md", "hunsu.json", "hunsu.lock.json", "hunsu-judgments.json",
                        "hunsu-conflicts.md", "hunsu.local.json", "marketplace.json", ".gitignore"}
        banned_dirs = {".chongdae", "reviews", ".dwitbuk", ".jokbo", ".mangsang", ".claude", ".codex", ".agents"}
        found = []
        for top, dnames, fnames in os.walk(PLUGIN):
            dnames[:] = [n for n in dnames if n != "__pycache__"]
            for n in dnames:
                if n in banned_dirs:
                    found.append(os.path.join(top, n))
            for n in fnames:
                if n in banned_files or (n.startswith("test_") and n.endswith(".py")):
                    found.append(os.path.join(top, n))
        self.assertEqual(found, [])

    def test_P1_no_symlink_in_payload(self):
        self.need_plugin()
        self.assertFalse(os.path.islink(PLUGIN), "plugin/ itself is a symlink")
        _, _, links = payload_entries()
        self.assertEqual(links, [], "symlinks under plugin/")

    def test_P2_runtime_and_manifests_moved_off_the_root(self):
        self.need_plugin()
        for rel in ("hacheong.py", "worker.py", "hostcall.py", "plugin.json", ".claude-plugin/plugin.json",
                    ".codex-plugin/plugin.json", "members", "domains", "skills"):
            self.assertTrue(os.path.lexists(os.path.join(PLUGIN, rel)), "plugin/%s missing" % rel)
        for rel in ("hostcall.py", "members", "domains", "skills", "plugin.json", ".claude-plugin/plugin.json", ".codex-plugin"):
            self.assertFalse(os.path.lexists(os.path.join(ROOT, rel)), "the repository root still has %s" % rel)

    def test_P2_root_claude_plugin_keeps_only_the_catalog(self):
        self.need_plugin()
        d = os.path.join(ROOT, ".claude-plugin")
        self.assertTrue(os.path.isfile(os.path.join(d, "marketplace.json")))
        self.assertNotIn("plugin.json", os.listdir(d))

    def test_P3_license_identical(self):
        self.need_plugin()
        a, b = os.path.join(ROOT, "LICENSE"), os.path.join(PLUGIN, "LICENSE")
        self.assertTrue(os.path.isfile(a), "root LICENSE missing")
        self.assertTrue(os.path.isfile(b), "plugin/LICENSE missing")
        with open(a, "rb") as fa, open(b, "rb") as fb:
            self.assertEqual(fa.read(), fb.read())

    def test_P5_payload_markdown_links_resolve_inside_payload(self):
        self.need_plugin()
        mds = []
        for top, dnames, fnames in os.walk(PLUGIN):
            dnames[:] = [n for n in dnames if n != "__pycache__"]
            mds += [os.path.join(top, n) for n in fnames if n.endswith(".md")]
        self.assertIn(os.path.join(PLUGIN, "README.md"), mds)
        bad = []
        for md in mds:
            for link in relative_links(md):
                if not link:
                    continue
                dest = os.path.join(os.path.dirname(md), link)
                if not inside(dest, PLUGIN) or not os.path.isfile(dest):
                    bad.append("%s -> %s" % (os.path.relpath(md, ROOT), link))
        self.assertEqual(bad, [])


def snapshot(top, skip=("__pycache__",)):
    seen = {}
    for d, dnames, fnames in os.walk(top):
        dnames[:] = [n for n in dnames if n not in skip]
        for n in fnames:
            p = os.path.join(d, n)
            st = os.lstat(p)
            seen[os.path.relpath(p, top)] = (st.st_size, st.st_mtime_ns)
    return seen


class P4SelfContained(Base):

    MARK = "PACKAGING-MARKER-%s-%s"

    def copy(self):
        self.need_plugin()
        dest = os.path.join(self.tmp(), "hacheong")
        shutil.copytree(PLUGIN, dest, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        self.assertFalse(inside(dest, ROOT))
        return dest

    def mark(self, copy, member):
        role_mark, dom_mark = self.MARK % ("ROLE", member), self.MARK % ("DOMAIN", member)
        with open(os.path.join(copy, "members", member, "ROLE.md"), "a", encoding="utf-8") as f:
            f.write("\n%s\n" % role_mark)
        dom = os.path.join(copy, "domains", "code", "DOMAIN.md")
        with open(dom, encoding="utf-8") as f:
            lines = f.read().split("\n")
        self.assertIn("## %s" % member, lines, "no ## %s section in the copy's domains/code/DOMAIN.md" % member)
        i = lines.index("## %s" % member)
        lines.insert(i + 1, dom_mark)
        with open(dom, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        return role_mark, dom_mark

    def guard_repo(self):
        before_plugin = snapshot(PLUGIN) if os.path.isdir(PLUGIN) else {}
        before_root = snapshot(ROOT, ("__pycache__", ".git", ".chongdae", "plugin"))
        def check():
            self.assertEqual(snapshot(PLUGIN) if os.path.isdir(PLUGIN) else {}, before_plugin, "the payload changed")
            self.assertEqual(snapshot(ROOT, ("__pycache__", ".git", ".chongdae", "plugin")), before_root, "the repository changed")
        return check

    def test_P4_copy_check_and_roster(self):
        copy = self.copy()
        cwd = self.tmp()
        guard = self.guard_repo()
        done = self.run_py(os.path.join(copy, "hacheong.py"), "check", cwd=cwd)
        self.assertEqual(done.returncode, 0, done.stderr.decode(errors="replace"))
        self.assertIn("4 member(s), 0 error(s)", done.stdout.decode() + done.stderr.decode())
        done = self.run_py(os.path.join(copy, "hacheong.py"), "roster", cwd=cwd)
        self.assertEqual(done.returncode, 0, done.stderr.decode(errors="replace"))
        out = done.stdout.decode()
        for role, m in ROLE_OF.items():
            self.assertRegex(out, r"(?m)^\s*%s\s+role:\s+%s\b" % (m, role))
        guard()

    def test_P4_copy_prompt_only_uses_copys_own_texts(self):
        copy = self.copy()
        cwd = self.tmp()
        target = self.repo()
        guard = self.guard_repo()
        for m in MEMBERS:
            role_mark, dom_mark = self.mark(copy, m)
            req = self.write_json(cwd, "req-%s.json" % m, request(target))
            done = self.run_py(os.path.join(copy, "worker.py"), "--member", m, "--request", req, "--response",
                               os.path.join(cwd, "resp-%s.json" % m), "--prompt-only", cwd=cwd)
            self.assertEqual(done.returncode, 0, done.stderr.decode(errors="replace"))
            out = done.stdout.decode()
            self.assertIn(role_mark, out, m)
            self.assertIn(dom_mark, out, m)
        guard()

    def test_P4_copy_runs_sibi_with_fake_claude(self):
        copy = self.copy()
        cwd = self.tmp()
        target = self.repo()
        role_mark, dom_mark = self.mark(copy, "sibi")
        bindir = self.tmp()
        fake = os.path.join(bindir, "claude")
        with open(fake, "w", encoding="utf-8") as f:
            f.write(FAKE_CLAUDE % (sys.executable, json.dumps(FAKE_RESULT)))
        os.chmod(fake, os.stat(fake).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        guard = self.guard_repo()
        req = self.write_json(cwd, "req.json", request(target))
        resp = os.path.join(cwd, "resp.json")
        env = clean_env(PATH=bindir + os.pathsep + os.environ.get("PATH", ""))
        done = self.run_py(os.path.join(copy, "worker.py"), "--member", "sibi", "--request", req, "--response", resp,
                           "--host", "claude", cwd=cwd, env=env)
        self.assertEqual(done.returncode, 0, done.stderr.decode(errors="replace"))
        self.assertTrue(os.path.isfile(resp), "no response written")
        with open(resp, encoding="utf-8") as f:
            out = json.load(f)
        self.assertEqual(out.get("status"), "done", out)
        self.assertEqual((out.get("worker") or {}).get("host"), "claude-code", out)
        self.assertTrue(os.path.isfile(os.path.join(bindir, "env.json")), "the fake claude was not started")
        with open(os.path.join(bindir, "env.json"), encoding="utf-8") as f:
            seen = json.load(f)
        self.assertEqual(seen, {"AGENT_WORKER": "1", "AGENT_HOST": "claude-code"})
        with open(os.path.join(bindir, "stdin.txt"), encoding="utf-8") as f:
            stdin = f.read()
        self.assertIn(role_mark, stdin)
        self.assertIn(dom_mark, stdin)
        guard()


class W1Entry(Base):

    def need_entries(self):
        self.need_plugin()
        for n in ("worker.py", "hacheong.py"):
            self.assertTrue(os.path.isfile(os.path.join(ROOT, n)), "root %s missing" % n)
            self.assertTrue(os.path.isfile(os.path.join(PLUGIN, n)), "plugin/%s missing" % n)

    def test_W1_worker_prompt_only_byte_identical(self):
        self.need_entries()
        cwd = self.tmp()
        target = self.repo()
        for m in MEMBERS:
            req = self.write_json(cwd, "req.json", request(target))
            args = ["--member", m, "--request", req, "--response", os.path.join(cwd, "r.json"), "--prompt-only"]
            a = self.run_py(os.path.join(ROOT, "worker.py"), *args, cwd=cwd)
            b = self.run_py(os.path.join(PLUGIN, "worker.py"), *args, cwd=cwd)
            self.assertEqual(b.returncode, 0, b.stderr.decode(errors="replace"))
            self.assertTrue(b.stdout, "no prompt printed")
            self.assertEqual(a.returncode, b.returncode, a.stderr.decode(errors="replace"))
            self.assertEqual(a.stdout, b.stdout, m)

    def test_W1_worker_invalid_request_exits_the_same(self):
        self.need_entries()
        cwd = self.tmp()
        bad = self.write_json(cwd, "bad.json", {"not": "a request"})
        args = ["--member", "sibi", "--request", bad, "--response", os.path.join(cwd, "r.json"), "--prompt-only"]
        a = self.run_py(os.path.join(ROOT, "worker.py"), *args, cwd=cwd)
        b = self.run_py(os.path.join(PLUGIN, "worker.py"), *args, cwd=cwd)
        self.assertNotEqual(b.returncode, 0)
        self.assertEqual(a.returncode, b.returncode)
        self.assertEqual(a.stdout, b.stdout)
        self.assertEqual(a.stderr, b.stderr)

    def test_W1_root_hacheong_check_and_roster(self):
        self.need_entries()
        cwd = self.tmp()
        done = self.run_py(os.path.join(ROOT, "hacheong.py"), "check", cwd=cwd)
        self.assertEqual(done.returncode, 0, done.stderr.decode(errors="replace"))
        self.assertIn("4 member(s), 0 error(s)", done.stdout.decode() + done.stderr.decode())
        a = self.run_py(os.path.join(ROOT, "hacheong.py"), "roster", cwd=cwd)
        b = self.run_py(os.path.join(PLUGIN, "hacheong.py"), "roster", cwd=cwd)
        self.assertEqual(a.returncode, 0, a.stderr.decode(errors="replace"))
        for role, m in ROLE_OF.items():
            self.assertRegex(a.stdout.decode(), r"(?m)^\s*%s\s+role:\s+%s\b" % (m, role))
        self.assertEqual(a.stdout, b.stdout)

    def test_W1_import_from_root_gives_payload_modules(self):
        self.need_entries()
        code = ("import json, os, sys\n"
                "sys.path.insert(0, %r)\n"
                "import worker, hacheong\n"
                "print(json.dumps({'worker': os.path.realpath(worker.__file__), 'hacheong': os.path.realpath(hacheong.__file__),"
                " 'same': hacheong.worker is worker, 'here': os.path.realpath(str(worker.HERE)),"
                " 'mods': [sys.modules['worker'] is worker, sys.modules['hacheong'] is hacheong]}))\n") % ROOT
        done = self.run_py("-I", "-c", code, cwd=self.tmp())
        self.assertEqual(done.returncode, 0, done.stderr.decode(errors="replace"))
        got = json.loads(done.stdout.decode().strip().splitlines()[-1])
        real = os.path.realpath(PLUGIN)
        self.assertEqual(got["worker"], os.path.join(real, "worker.py"))
        self.assertEqual(got["hacheong"], os.path.join(real, "hacheong.py"))
        self.assertTrue(got["same"], "hacheong.worker is not worker")
        self.assertEqual(got["here"], real)
        self.assertEqual(got["mods"], [True, True])


class W2Shim(Base):

    def test_W2_entry_points_hold_no_runtime(self):
        self.need_plugin()
        for n in ("worker.py", "hacheong.py"):
            p = os.path.join(ROOT, n)
            self.assertTrue(os.path.isfile(p), n)
            with open(p, encoding="utf-8") as f:
                src = f.read()
            self.assertLess(len(src.splitlines()), 40, "%s has %d lines" % (n, len(src.splitlines())))
            tree = ast.parse(src)
            defs = [type(x).__name__ for x in ast.walk(tree) if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
            self.assertEqual(defs, [], n)
            doc = ast.get_docstring(tree) or ""
            self.assertIn("plugin/", doc, n)
            self.assertIn("compatib", doc.lower(), n)
            self.assertIn("run_path", src, n)
            self.assertIn("__main__", src, n)
            self.assertIn("sys.modules", src, n)

    def test_W2_no_other_root_shim(self):
        self.need_plugin()
        self.assertFalse(os.path.lexists(os.path.join(ROOT, "hostcall.py")))


class T1Suites(Base):

    PROBE = r'''
import importlib.util, json, os, sys
root, suite = sys.argv[1], sys.argv[2]
os.chdir(root)
sys.path.insert(0, root)
spec = importlib.util.spec_from_file_location("suite_probe_" + suite[:-3], os.path.join(root, suite))
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
found = []
class Seen:
    @staticmethod
    def find_spec(name, path=None, target=None):
        if name in ("worker", "hacheong", "hostcall"):
            s = importlib.machinery.PathFinder.find_spec(name, path)
            found.append([name, os.path.realpath(s.origin) if s and s.origin else None])
        return None
import importlib.machinery
sys.meta_path.insert(0, Seen)
spec.loader.exec_module(mod)
sys.meta_path.remove(Seen)
got = {m: os.path.realpath(sys.modules[m].__file__) for m in ("worker", "hacheong", "hostcall") if m in sys.modules}
print(json.dumps({"mods": got, "found": found, "path0": os.path.realpath(sys.path[0]),
                  "ROOT": os.path.realpath(getattr(mod, "ROOT", "")) if getattr(mod, "ROOT", None) else None,
                  "PLUGIN": os.path.realpath(getattr(mod, "PLUGIN", "")) if getattr(mod, "PLUGIN", None) else None,
                  "HERE": os.path.realpath(str(mod.HERE)) if isinstance(getattr(mod, "HERE", None), str) else None}))
'''

    def test_T1_suites_stay_at_root_and_import_from_plugin(self):
        self.need_plugin()
        real = os.path.realpath(PLUGIN)
        for suite in SUITES:
            with self.subTest(suite=suite):
                self.assertTrue(os.path.isfile(os.path.join(ROOT, suite)), "%s is not at the root" % suite)
                self.assertFalse(os.path.lexists(os.path.join(PLUGIN, suite)))
                done = self.run_py("-I", "-c", self.PROBE, ROOT, suite, cwd=ROOT)
                self.assertEqual(done.returncode, 0, done.stderr.decode(errors="replace")[-3000:])
                got = json.loads(done.stdout.decode().strip().splitlines()[-1])
                self.assertTrue(got["mods"], "%s imports none of worker, hacheong, hostcall" % suite)
                for m, f in got["mods"].items():
                    self.assertEqual(f, os.path.join(real, m + ".py"), "%s: %s comes from %s" % (suite, m, f))
                for m, f in got["found"]:
                    self.assertEqual(f, os.path.join(real, m + ".py"), "%s: import %s found %s first" % (suite, m, f))
                self.assertEqual(got["path0"], real, "%s: sys.path[0] is %s" % (suite, got["path0"]))
                self.assertEqual(got["ROOT"], os.path.realpath(ROOT), suite)
                self.assertEqual(got["PLUGIN"], real, suite)

    def probe(self, suite):
        done = self.run_py("-I", "-c", self.PROBE, ROOT, suite, cwd=ROOT)
        self.assertEqual(done.returncode, 0, done.stderr.decode(errors="replace")[-3000:])
        return json.loads(done.stdout.decode().strip().splitlines()[-1])

    def test_T1_suites_do_not_name_root_entry_points(self):
        self.need_plugin()
        bad = []
        for suite in SUITES:
            with open(os.path.join(ROOT, suite), encoding="utf-8") as f:
                src = f.read()
            # HERE counts as the root only where the suite has it pointing at the root
            names = "ROOT|HERE" if self.probe(suite)["HERE"] == os.path.realpath(ROOT) else "ROOT"
            for pat in (r"os\.path\.join\(\s*(NAMES)\s*,\s*[\"'](worker|hacheong|hostcall)\.py[\"']",
                        r"os\.path\.join\(\s*(NAMES)\s*,\s*[\"'](members|domains|skills)[\"']",
                        r"Path\(\s*(NAMES)\s*\)\s*/\s*[\"'](members|domains|skills)[\"']"):
                for hit in re.finditer(pat.replace("NAMES", names), src):
                    bad.append("%s: %s" % (suite, hit.group(0)))
        self.assertEqual(bad, [], "suites reaching runtime files at the root")


class T2RedGate(Base):

    def g7(self):
        p = os.path.join(ROOT, "test_red_gate.py")
        self.assertTrue(os.path.isfile(p))
        with open(p, encoding="utf-8") as f:
            src = f.read()
        fn = [x for x in ast.walk(ast.parse(src)) if isinstance(x, ast.FunctionDef)
              and x.name == "test_G7_previous_slices_tests_unchanged_and_passing"]
        self.assertEqual(len(fn), 1, "G7 test not found once")
        return src, fn[0]

    def test_T2_G7_no_longer_diffs_against_head(self):
        src, fn = self.g7()
        for call in [x for x in ast.walk(fn) if isinstance(x, ast.Call)]:
            consts = {c.value for c in ast.walk(call) if isinstance(c, ast.Constant) and isinstance(c.value, str)}
            self.assertFalse({"--quiet", "HEAD"} & consts and "diff" in consts, "G7 still runs git diff --quiet HEAD")
            self.assertNotIn("HEAD", consts, "G7 still compares with HEAD")
        lines = src.splitlines()[fn.lineno - 1:fn.end_lineno]
        comments = [t.string for t in tokenize.generate_tokens(io.StringIO("\n".join(lines) + "\n").readline)
                    if t.type == tokenize.COMMENT]
        self.assertTrue(comments, "G7 has no comment saying why the HEAD comparison went")

    def test_T2_G7_still_runs_the_three_suites(self):
        src, fn = self.g7()
        consts = {c.value for c in ast.walk(fn) if isinstance(c, ast.Constant) and isinstance(c.value, str)}
        for f in ("test_record_paths.py", "test_native_prompt.py", "test_hostcall_env.py"):
            self.assertIn(f, consts)
        runs = [c for c in ast.walk(fn) if isinstance(c, ast.Call)
                and {"-m", "unittest"} <= {k.value for k in ast.walk(c) if isinstance(k, ast.Constant)}]
        self.assertTrue(runs, "G7 no longer runs -m unittest")
        self.assertTrue(any(k.arg == "cwd" for c in runs for k in c.keywords), "G7 runs the suites without a cwd")
        self.assertIn("returncode", ast.get_source_segment(src, fn))


class M_Manifests(Base):

    def entry(self, catalog):
        hits = [p for p in catalog.get("plugins", []) if p.get("name") == "hacheong"]
        self.assertEqual(len(hits), 1, catalog)
        return hits[0]

    def test_M1_claude_marketplace_source_is_plugin(self):
        cat = self.read_json(ROOT, ".claude-plugin", "marketplace.json")
        e = self.entry(cat)
        self.assertEqual(e.get("source"), "./plugin")
        self.assertEqual(set(cat), {"name", "owner", "metadata", "plugins"})
        self.assertEqual(set(e), {"name", "source", "version", "description"})
        self.assertFalse(os.path.lexists(os.path.join(PLUGIN, ".claude-plugin", "marketplace.json")))

    def test_M1_agents_marketplace_source_path_is_plugin(self):
        cat = self.read_json(ROOT, ".agents", "plugins", "marketplace.json")
        e = self.entry(cat)
        self.assertEqual(e.get("source"), {"source": "local", "path": "./plugin"})
        self.assertEqual(set(cat), {"name", "interface", "plugins"})
        self.assertEqual(set(e), {"name", "source", "policy", "category"})
        self.assertFalse(os.path.lexists(os.path.join(PLUGIN, ".agents")))

    def manifests(self):
        self.need_plugin()
        return [self.read_json(PLUGIN, "plugin.json"), self.read_json(PLUGIN, ".claude-plugin", "plugin.json"),
                self.read_json(PLUGIN, ".codex-plugin", "plugin.json")]

    def test_M2_payload_manifests_agree(self):
        ms = self.manifests()
        self.assertEqual(ms[0].get("name"), "hacheong")
        for k in ("name", "version", "engines", "records", "roles"):
            for m in ms[1:]:
                self.assertIn(k, m)
                self.assertEqual(m[k], ms[0][k], k)

    def test_M2_marketplace_version_matches_payload(self):
        v = self.manifests()[0].get("version")
        self.assertTrue(v)
        cat = self.read_json(ROOT, ".claude-plugin", "marketplace.json")
        self.assertEqual(cat["metadata"]["version"], v)
        self.assertEqual(self.entry(cat)["version"], v)

    def test_M2_roles_argv_and_members(self):
        roles = self.manifests()[0]["roles"]
        mdir = os.path.join(PLUGIN, "members")
        self.assertTrue(os.path.isdir(mdir))
        on_disk = {n for n in os.listdir(mdir) if os.path.isdir(os.path.join(mdir, n)) and n != "__pycache__"}
        self.assertEqual({r: argv[3] for r, argv in roles.items()}, ROLE_OF)
        for r, argv in roles.items():
            self.assertEqual(argv, ["python3", "{plugin:hacheong}/worker.py", "--member", ROLE_OF[r], "--request", "{request}",
                                    "--response", "{response}", "--host", "{host}"], r)
            self.assertIn(argv[3], on_disk)
        self.assertEqual({argv[3] for argv in roles.values()}, on_disk)

    def test_M2_codex_skills_resolve_in_payload(self):
        codex = self.manifests()[2]
        self.assertEqual(codex.get("skills"), "./skills/")
        p = os.path.normpath(os.path.join(PLUGIN, codex["skills"]))
        self.assertEqual(p, os.path.join(PLUGIN, "skills"))
        self.assertTrue(os.path.isfile(os.path.join(p, "hire", "SKILL.md")))


class D_RootLinks(Base):

    def test_D2_D3_root_readme_and_agents_links_resolve(self):
        bad = []
        for n in ("README.md", "AGENTS.md"):
            p = os.path.join(ROOT, n)
            self.assertTrue(os.path.isfile(p), n)
            for link in relative_links(p):
                if link and not os.path.isfile(os.path.join(ROOT, link)):
                    bad.append("%s -> %s" % (n, link))
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()
