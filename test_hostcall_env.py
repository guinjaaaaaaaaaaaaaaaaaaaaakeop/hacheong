"""Worker host calls start each child with its own host identity, not the parent's (H1-H6, S4).

  python3 -m unittest test_hostcall_env.py
"""
import ast
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
import hostcall  # noqa: E402

IDENTITY = ("CODEX_THREAD_ID", "CODEX_SESSION_ID", "CLAUDE_CODE_SESSION_ID", "CHONGDAE_SESSION", "AI_AGENT", "CLAUDE_PROJECT_DIR", "CODEX_VERSION")

BASE = {
    "HOME": "/home/synthetic",
    "PATH": "/usr/bin:/bin",
    "CODEX_HOME": "/home/synthetic/.codex",
    "AGENT_CODEX_HOME": "/home/synthetic/.agent-codex",
    "CLAUDE_CONFIG_DIR": "/home/synthetic/.claude",
    "ANTHROPIC_API_KEY": "sk-ant-synthetic-0000",
    "OPENAI_API_KEY": "sk-openai-synthetic-0000",
    "CODEX_API_KEY": "codex-synthetic-0000",
    "ANTHROPIC_MODEL": "synthetic-model",
    "CLAUDE_CODE_USE_BEDROCK": "0",
    "CODEX_MODEL": "synthetic-codex-model",
    "CODEX_THREAD_ID_NOTE": "near-miss-keep",
    "CODEX_SESSION_ID_NOTE": "near-miss-keep",
    "CHONGDAE_WAIT": "near-miss-keep",
    "UNRELATED_VALUE": "keep me",
}
CLAUDE_PARENT = dict(BASE, AGENT_HOST="claude-code", CLAUDE_CODE_SESSION_ID="parent-claude", AI_AGENT="claude-code",
                     CLAUDE_PROJECT_DIR="/work/parent-project", CLAUDECODE="1")
CODEX_PARENT = dict(BASE, AGENT_HOST="codex", CODEX_THREAD_ID="parent-codex", CODEX_SESSION_ID="parent-codex-session",
                    CODEX_VERSION="0.99.0")
CLAUDE_BY_CODEX_PARENT = dict(CLAUDE_PARENT, CODEX_SESSION_ID="parent-codex-session")
MIXED_PARENT = dict(BASE, AGENT_HOST="claude-code", CODEX_THREAD_ID="parent-codex", CODEX_SESSION_ID="parent-codex-session",
                    CODEX_VERSION="0.99.0",
                    CLAUDE_CODE_SESSION_ID="parent-claude", AI_AGENT="claude-code", CLAUDE_PROJECT_DIR="/work/parent-project",
                    CLAUDECODE="1", CHONGDAE_SESSION="parent-override")
BARE_PARENT = dict(BASE)
PARENTS = {"claude": CLAUDE_PARENT, "codex": CODEX_PARENT, "claude-by-codex": CLAUDE_BY_CODEX_PARENT, "mixed": MIXED_PARENT,
           "bare": BARE_PARENT}
SESSION_PARENTS = {"codex": CODEX_PARENT, "claude-by-codex": CLAUDE_BY_CODEX_PARENT, "mixed": MIXED_PARENT}

SCHEMA = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}


def minus_identity(p):
    return {k: v for k, v in p.items() if k not in IDENTITY}


def done(cmd, rc=0, out=b"out \xe2\x9c\x93", err=b"err \xff"):
    return subprocess.CompletedProcess(cmd, rc, out, err)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="hostcall-env-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.beside = os.path.join(self.tmp, "r.json")

    def parent(self, env):
        """Replace os.environ with exactly env for the rest of the test; restored afterwards."""
        p = mock.patch.dict(os.environ, env, clear=True)
        p.start()
        self.addCleanup(p.stop)

    def call_codex(self, write_last=None, **kw):
        seen = {}

        def fake(cmd, *a, **k):
            seen["cmd"], seen["args"], seen["kw"] = cmd, a, k
            if "-o" in cmd and write_last is not None:
                with open(cmd[cmd.index("-o") + 1], "w", encoding="utf-8") as f:
                    f.write(write_last)
            if "--output-schema" in cmd:
                sp = cmd[cmd.index("--output-schema") + 1]
                seen["schema_text"] = None
                if os.path.exists(sp):
                    with open(sp, encoding="utf-8") as f:
                        seen["schema_text"] = f.read()
            return done(cmd)

        args = dict(cwd=self.tmp, beside=self.beside)
        args.update(kw)
        with mock.patch("subprocess.run", side_effect=fake) as m:
            ret = hostcall.run_codex("prompt ✓", SCHEMA, **args)
        self.assertEqual(m.call_count, 1)
        return seen, ret

    def call_claude(self, **kw):
        seen = {}

        def fake(cmd, *a, **k):
            seen["cmd"], seen["args"], seen["kw"] = cmd, a, k
            return done(cmd)

        args = dict(cwd=self.tmp)
        args.update(kw)
        with mock.patch("subprocess.run", side_effect=fake) as m:
            ret = hostcall.run_claude("prompt ✓", SCHEMA, **args)
        self.assertEqual(m.call_count, 1)
        return seen, ret


class H1WorkerEnv(Base):
    def test_H1_codex_env_is_parent_minus_identity_plus_codex(self):
        for name, p in PARENTS.items():
            with self.subTest(parent=name):
                with mock.patch.dict(os.environ, p, clear=True):
                    got = hostcall.worker_env("codex")
                    self.assertEqual(got, dict(minus_identity(p), AGENT_HOST="codex", AGENT_WORKER="1"))
                    self.assertIsNot(got, os.environ)

    def test_H1_claude_env_is_parent_minus_identity_plus_claude_code(self):
        for name, p in PARENTS.items():
            with self.subTest(parent=name):
                with mock.patch.dict(os.environ, p, clear=True):
                    got = hostcall.worker_env("claude")
                    self.assertEqual(got, dict(minus_identity(p), AGENT_HOST="claude-code", AGENT_WORKER="1"))
                    self.assertIsNot(got, os.environ)

    def test_H1_other_host_raises_value_error(self):
        self.parent(MIXED_PARENT)
        for bad in ("claude-code", "Codex", "", "gemini", None):
            with self.subTest(host=bad):
                with self.assertRaises(ValueError):
                    hostcall.worker_env(bad)
        self.assertEqual(dict(os.environ), MIXED_PARENT)

    def test_H1_returns_a_new_dict_each_call(self):
        self.parent(CLAUDE_PARENT)
        a = hostcall.worker_env("codex")
        b = hostcall.worker_env("codex")
        self.assertIsInstance(a, dict)
        self.assertIsNot(a, b)
        a["MUTATED"] = "x"
        self.assertNotIn("MUTATED", hostcall.worker_env("codex"))
        self.assertNotIn("MUTATED", os.environ)

    def test_H1_never_changes_os_environ(self):
        self.parent(MIXED_PARENT)
        hostcall.worker_env("codex")
        hostcall.worker_env("claude")
        self.assertEqual(dict(os.environ), MIXED_PARENT)

    def test_H1_reads_parent_at_call_time(self):
        self.parent(BARE_PARENT)
        os.environ["LATE_VALUE"] = "late"
        os.environ["CODEX_THREAD_ID"] = "late-thread"
        got = hostcall.worker_env("claude")
        self.assertEqual(got.get("LATE_VALUE"), "late")
        self.assertNotIn("CODEX_THREAD_ID", got)

    def test_H1_self_contained_no_plugin_or_worker_import(self):
        self.assertTrue(callable(getattr(hostcall, "worker_env", None)), "hostcall.worker_env is missing")
        with open(os.path.join(HERE, "hostcall.py"), encoding="utf-8") as f:
            tree = ast.parse(f.read())
        stdlib = set(getattr(sys, "stdlib_module_names", ())) or {"json", "os", "re", "shutil", "subprocess", "tempfile", "pathlib"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                self.assertEqual(node.level, 0, "relative import in hostcall.py")
                names = [node.module or ""]
            else:
                continue
            for n in names:
                top = n.split(".")[0]
                self.assertNotEqual(top, "worker", "hostcall.py imports worker.py")
                self.assertIn(top, stdlib, "hostcall.py imports non-stdlib module %r" % n)


class H2RunCodexEnv(Base):
    def test_H2_env_is_exactly_parent_minus_identity_plus_codex(self):
        for name, p in PARENTS.items():
            with self.subTest(parent=name):
                with mock.patch.dict(os.environ, p, clear=True):
                    seen, _ = self.call_codex()
                self.assertEqual(seen["kw"].get("env"), dict(minus_identity(p), AGENT_HOST="codex", AGENT_WORKER="1"))

    def test_H2_does_not_add_disable_auto_memory(self):
        self.parent(MIXED_PARENT)
        seen, _ = self.call_codex()
        self.assertNotIn("CLAUDE_CODE_DISABLE_AUTO_MEMORY", seen["kw"]["env"])

    def test_H2_keeps_parent_disable_auto_memory_as_is(self):
        p = dict(MIXED_PARENT, CLAUDE_CODE_DISABLE_AUTO_MEMORY="0")
        self.parent(p)
        seen, _ = self.call_codex()
        self.assertEqual(seen["kw"]["env"]["CLAUDE_CODE_DISABLE_AUTO_MEMORY"], "0")
        self.assertEqual(seen["kw"]["env"], dict(minus_identity(p), AGENT_HOST="codex", AGENT_WORKER="1"))

    def test_H2_reproduction_identity_keys_not_inherited(self):
        self.parent(MIXED_PARENT)
        seen, _ = self.call_codex()
        env = seen["kw"]["env"]
        for k in IDENTITY:
            self.assertNotIn(k, env)
        self.assertEqual(env["AGENT_HOST"], "codex")
        self.assertEqual(env.get("AGENT_WORKER"), "1")


class H3RunClaudeEnv(Base):
    def test_H3_env_is_exactly_parent_minus_identity_plus_claude(self):
        for name, p in PARENTS.items():
            with self.subTest(parent=name):
                with mock.patch.dict(os.environ, p, clear=True):
                    seen, _ = self.call_claude()
                self.assertEqual(seen["kw"].get("env"), dict(minus_identity(p), AGENT_HOST="claude-code", AGENT_WORKER="1",
                                                             CLAUDE_CODE_DISABLE_AUTO_MEMORY="1"))

    def test_H3_disable_auto_memory_overrides_parent_zero(self):
        p = dict(CODEX_PARENT, CLAUDE_CODE_DISABLE_AUTO_MEMORY="0")
        self.parent(p)
        seen, _ = self.call_claude()
        self.assertEqual(seen["kw"]["env"], dict(minus_identity(p), AGENT_HOST="claude-code", AGENT_WORKER="1",
                                                 CLAUDE_CODE_DISABLE_AUTO_MEMORY="1"))

    def test_H3_reproduction_identity_keys_not_inherited(self):
        self.parent(MIXED_PARENT)
        seen, _ = self.call_claude()
        env = seen["kw"]["env"]
        for k in IDENTITY:
            self.assertNotIn(k, env)
        self.assertEqual(env["AGENT_HOST"], "claude-code")
        self.assertEqual(env.get("AGENT_WORKER"), "1")


class H4AnyParent(Base):
    KEEP = ("HOME", "PATH", "CODEX_HOME", "AGENT_CODEX_HOME", "CLAUDE_CONFIG_DIR", "ANTHROPIC_API_KEY", "OPENAI_API_KEY",
            "CODEX_API_KEY", "ANTHROPIC_MODEL", "CLAUDE_CODE_USE_BEDROCK", "CODEX_MODEL", "CODEX_THREAD_ID_NOTE",
            "CODEX_SESSION_ID_NOTE", "CHONGDAE_WAIT", "UNRELATED_VALUE")

    def check(self, p, child):
        with mock.patch.dict(os.environ, p, clear=True):
            seen, _ = self.call_codex() if child == "codex" else self.call_claude()
        env = seen["kw"]["env"]
        self.assertEqual(env.get("AGENT_HOST"), "codex" if child == "codex" else "claude-code")
        self.assertEqual(env.get("AGENT_WORKER"), "1")
        for k in IDENTITY:
            self.assertNotIn(k, env)
        for k in self.KEEP:
            self.assertEqual(env.get(k), p.get(k), k)
        if "CLAUDECODE" in p:
            self.assertEqual(env.get("CLAUDECODE"), p["CLAUDECODE"])
        else:
            self.assertNotIn("CLAUDECODE", env)
        return env

    def test_H4_claude_parent_cross_host_codex_child(self):
        self.check(CLAUDE_PARENT, "codex")

    def test_H4_claude_parent_same_host_claude_child(self):
        self.check(CLAUDE_PARENT, "claude")

    def test_H4_codex_parent_cross_host_claude_child(self):
        self.check(CODEX_PARENT, "claude")

    def test_H4_codex_parent_same_host_codex_child(self):
        self.check(CODEX_PARENT, "codex")

    def test_H4_mixed_parent_both_children(self):
        self.check(MIXED_PARENT, "codex")
        self.check(MIXED_PARENT, "claude")

    def test_H4_claude_parent_launched_by_codex_both_children(self):
        self.check(CLAUDE_BY_CODEX_PARENT, "codex")
        self.check(CLAUDE_BY_CODEX_PARENT, "claude")

    def test_H4_every_parent_kind_both_children(self):
        for name, p in PARENTS.items():
            for child in ("codex", "claude"):
                with self.subTest(parent=name, child=child):
                    self.check(p, child)

    def test_H4_bare_parent_both_children(self):
        self.check(BARE_PARENT, "codex")
        self.check(BARE_PARENT, "claude")

    def test_H4_claudecode_kept_with_its_value_and_never_added(self):
        self.assertEqual(self.check(dict(CODEX_PARENT, CLAUDECODE="weird"), "claude")["CLAUDECODE"], "weird")
        self.assertEqual(self.check(dict(CODEX_PARENT, CLAUDECODE="weird"), "codex")["CLAUDECODE"], "weird")
        self.assertNotIn("CLAUDECODE", self.check(CODEX_PARENT, "claude"))
        self.assertNotIn("CLAUDECODE", self.check(CODEX_PARENT, "codex"))

    def test_H4_sandbox_setting_kept_in_env(self):
        p = dict(CLAUDE_PARENT, AGENT_CODEX_SANDBOX="workspace-write")
        self.assertEqual(self.check(p, "codex")["AGENT_CODEX_SANDBOX"], "workspace-write")
        self.assertEqual(self.check(p, "claude")["AGENT_CODEX_SANDBOX"], "workspace-write")


class S4SessionIdKey(Base):
    """The literal key "CODEX_SESSION_ID" never reaches a child, whichever host starts it."""

    def assert_child_env(self, env, p, host):
        self.assertNotIn("CODEX_SESSION_ID", env)
        self.assertFalse(any(k == "CODEX_SESSION_ID" for k in env), "CODEX_SESSION_ID inherited by the child env")
        self.assertEqual(env.get("CODEX_SESSION_ID_NOTE"), p["CODEX_SESSION_ID_NOTE"])
        self.assertEqual(env.get("CODEX_SESSION_ID_NOTE"), "near-miss-keep")
        self.assertEqual(env.get("CODEX_THREAD_ID_NOTE"), "near-miss-keep")
        self.assertEqual(env.get("CHONGDAE_WAIT"), "near-miss-keep")
        self.assertEqual(env.get("AGENT_HOST"), host)

    def test_S4_run_claude_drops_codex_session_id(self):
        for name, p in SESSION_PARENTS.items():
            with self.subTest(parent=name):
                self.assertEqual(p.get("CODEX_SESSION_ID"), "parent-codex-session")
                with mock.patch.dict(os.environ, p, clear=True):
                    self.assertEqual(os.environ.get("CODEX_SESSION_ID"), "parent-codex-session")
                    seen, _ = self.call_claude()
                    self.assertEqual(os.environ.get("CODEX_SESSION_ID"), "parent-codex-session")
                self.assert_child_env(seen["kw"]["env"], p, "claude-code")

    def test_S4_run_codex_drops_codex_session_id(self):
        for name, p in SESSION_PARENTS.items():
            with self.subTest(parent=name):
                with mock.patch.dict(os.environ, p, clear=True):
                    seen, _ = self.call_codex()
                    self.assertEqual(os.environ.get("CODEX_SESSION_ID"), "parent-codex-session")
                self.assert_child_env(seen["kw"]["env"], p, "codex")

    def test_S4_worker_env_both_hosts_drop_codex_session_id(self):
        for name, p in SESSION_PARENTS.items():
            for host, agent in (("claude", "claude-code"), ("codex", "codex")):
                with self.subTest(parent=name, host=host):
                    with mock.patch.dict(os.environ, p, clear=True):
                        env = hostcall.worker_env(host)
                        self.assertEqual(os.environ.get("CODEX_SESSION_ID"), "parent-codex-session")
                    self.assert_child_env(env, p, agent)

    def test_S4_session_id_alone_in_bare_parent_is_dropped(self):
        p = dict(BARE_PARENT, CODEX_SESSION_ID="lonely-session")
        self.parent(p)
        seen_claude, _ = self.call_claude()
        seen_codex, _ = self.call_codex()
        self.assertNotIn("CODEX_SESSION_ID", seen_claude["kw"]["env"])
        self.assertNotIn("CODEX_SESSION_ID", seen_codex["kw"]["env"])
        self.assertEqual(seen_codex["kw"]["env"], dict(BARE_PARENT, AGENT_HOST="codex", AGENT_WORKER="1"))
        self.assertEqual(dict(os.environ), p)

    def test_S4_empty_session_id_is_still_dropped(self):
        self.parent(dict(CODEX_PARENT, CODEX_SESSION_ID=""))
        seen, _ = self.call_claude()
        self.assertNotIn("CODEX_SESSION_ID", seen["kw"]["env"])
        self.assertNotIn("CODEX_SESSION_ID", hostcall.worker_env("codex"))


class H5NoMutation(Base):
    def test_H5_run_codex_does_not_mutate_os_environ(self):
        self.parent(MIXED_PARENT)
        before = dict(os.environ)
        seen, _ = self.call_codex()
        self.assertEqual(dict(os.environ), before)
        self.assertIsNot(seen["kw"].get("env"), os.environ)
        self.assertIsNotNone(seen["kw"].get("env"))

    def test_H5_run_claude_does_not_mutate_os_environ(self):
        self.parent(MIXED_PARENT)
        before = dict(os.environ)
        seen, _ = self.call_claude()
        self.assertEqual(dict(os.environ), before)
        self.assertIsNot(seen["kw"].get("env"), os.environ)
        self.assertIsNotNone(seen["kw"].get("env"))

    def test_H5_both_in_sequence_do_not_mutate_and_do_not_leak(self):
        self.parent(MIXED_PARENT)
        before = dict(os.environ)
        s1, _ = self.call_codex()
        s2, _ = self.call_claude()
        s3, _ = self.call_codex()
        self.assertEqual(dict(os.environ), before)
        self.assertNotIn("CLAUDE_CODE_DISABLE_AUTO_MEMORY", s3["kw"]["env"])
        self.assertEqual(s1["kw"]["env"], s3["kw"]["env"])
        self.assertEqual(s2["kw"]["env"]["AGENT_HOST"], "claude-code")
        for s in (s1, s2, s3):
            self.assertIsNot(s["kw"]["env"], os.environ)


class H6Preservation(Base):
    def test_H6_run_claude_argv_and_kwargs(self):
        self.parent(BARE_PARENT)
        seen, ret = self.call_claude(add_dirs=("/a", "/b c"), tools="Read,Bash", model="opus-x", effort="high",
                                     max_turns=7, bypass=True)
        tools = "Read,Bash"
        self.assertEqual(seen["cmd"], ["claude", "-p", "--output-format", "stream-json", "--verbose", "--no-session-persistence",
                                       "--setting-sources", "", "--strict-mcp-config", "--tools", tools, "--allowedTools", tools,
                                       "--max-turns", "7", "--json-schema", json.dumps(SCHEMA), "--model", "opus-x",
                                       "--effort", "high", "--add-dir", "/a", "--add-dir", "/b c",
                                       "--permission-mode", "bypassPermissions"])
        self.assertEqual(seen["args"], ())
        self.assertEqual(set(seen["kw"]), {"input", "capture_output", "cwd", "env"})
        self.assertEqual(seen["kw"]["input"], "prompt ✓".encode("utf-8"))
        self.assertIs(seen["kw"]["capture_output"], True)
        self.assertEqual(seen["kw"]["cwd"], self.tmp)
        self.assertEqual(ret, (0, "out ✓", "err �"))

    def test_H6_run_claude_minimal_argv(self):
        self.parent(BARE_PARENT)
        seen, _ = self.call_claude()
        t = "Read,Grep,Glob"
        self.assertEqual(seen["cmd"], ["claude", "-p", "--output-format", "stream-json", "--verbose", "--no-session-persistence",
                                       "--setting-sources", "", "--strict-mcp-config", "--tools", t, "--allowedTools", t,
                                       "--max-turns", "30", "--json-schema", json.dumps(SCHEMA)])

    def test_H6_run_codex_argv_kwargs_files_and_return(self):
        self.parent(dict(BARE_PARENT))
        exe = shutil.which("codex") or "codex"
        stem = os.path.join(self.tmp, "r")
        seen, ret = self.call_codex(write_last="last ✓", add_dirs=("/a", "/b"), sandbox="workspace-write",
                                    model="gpt-x", effort="medium")
        self.assertEqual(seen["cmd"], [exe, "exec", "--json", "-C", self.tmp, "-s", "workspace-write", "--skip-git-repo-check",
                                       "--output-schema", stem + ".schema.json", "-o", stem + ".last.txt",
                                       "-m", "gpt-x", "-c", "model_reasoning_effort=" + json.dumps("medium"),
                                       "--add-dir", "/a", "--add-dir", "/b", "-"])
        self.assertEqual(seen["schema_text"], json.dumps(SCHEMA))
        self.assertEqual(seen["args"], ())
        self.assertEqual(set(seen["kw"]), {"input", "capture_output", "env"})
        self.assertEqual(seen["kw"]["input"], "prompt ✓".encode("utf-8"))
        self.assertIs(seen["kw"]["capture_output"], True)
        self.assertEqual(ret, (0, "out ✓", "err �", "last ✓"))

    def test_H6_run_codex_parent_sandbox_overrides_and_last_absent_is_none(self):
        self.parent(dict(BARE_PARENT, AGENT_CODEX_SANDBOX="danger-full-access"))
        exe = shutil.which("codex") or "codex"
        stem = os.path.join(self.tmp, "r")
        seen, ret = self.call_codex(sandbox="read-only")
        self.assertEqual(seen["cmd"], [exe, "exec", "--json", "-C", self.tmp, "-s", "danger-full-access", "--skip-git-repo-check",
                                       "--output-schema", stem + ".schema.json", "-o", stem + ".last.txt", "-"])
        self.assertEqual(ret, (0, "out ✓", "err �", None))

    def test_H6_claude_answer_and_worker_record_still_present(self):
        self.assertTrue(callable(hostcall.claude_answer))
        self.assertTrue(callable(hostcall.worker_record))


if __name__ == "__main__":
    unittest.main()
