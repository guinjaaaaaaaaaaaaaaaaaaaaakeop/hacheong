"""--prompt-only describes a neutral native environment; the subprocess renderings stay as they were (N1-N7).

  python3 -m unittest test_native_prompt.py
"""
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.join(ROOT, "plugin")
sys.path.insert(0, PLUGIN)
import worker  # noqa: E402

MEMBERS = ("dakdol", "sibi", "teujip", "chojja")
TOOLS = {"dakdol": "Read,Edit,Write,Glob,Grep,Bash", "teujip": "Read,Edit,Write,Glob,Grep,Bash", "sibi": "Read,Grep,Glob", "chojja": "Bash,Read"}
SANDBOX = {"dakdol": "workspace-write", "teujip": "workspace-write", "chojja": "workspace-write", "sibi": "read-only"}

S = ("What the work needs and this place lacks — a package, a tool, the network, a file outside `target` — is not yours to work "
     "around: stop with `status: blocked` and name it. When it is the network or loopback, list it in `lacked` (`[\"loopback\"]`, "
     "`[\"network\"]`), not only in prose — the runner reads `lacked`, not your sentences; nothing lacked: `lacked: []`. Do not "
     "write by hand what a tool generates (a lock file, a build output) and do not swap in another tool for the one the request names.")
NATIVE = ("# Where you run\n\n"
          "You are a subagent the parent session dispatched itself (a native call); this prompt was printed by `worker.py --prompt-only`, "
          "which grants nothing. What you may read, write and run, your tools, and whether you have the network or loopback (binding a "
          "local port) come from the parent host and its configuration, not from this text. This runner starts no subprocess for you — "
          "none of its sandboxes applies — and runs none of its validators on your answer.\n" + S)
CLAUDE_L2 = "Network: yes. Loopback — binding a local port (a local server, `wrangler dev`, a fake S3 on 127.0.0.1): yes."
CODEX_L2 = "Network: no. Loopback — binding a local port (a local server, `wrangler dev`, a fake S3 on 127.0.0.1): no."
CODEX_L1 = {"workspace-write": "A Codex sandbox (`workspace-write`): you can write inside `target`. By default it has no network — package "
                               "installs and downloads fail — and `.git` is read-only: no commit, no `git mv`, no branch.",
            "read-only": "A Codex sandbox (`read-only`): you can read and run commands, not write, and there is no network."}
FORBIDDEN = ("A Claude Code session with these tools only", "Network: yes", "Network: no", "Loopback — binding a local port",
             "A Codex sandbox", "`read-only`", "`workspace-write`", "no network")
REQUEST_LINE = "Work only inside `target`. Do not write the response file; answer with the JSON object."


def expected_env(member, host):
    if host == "codex":
        l1, l2 = CODEX_L1[SANDBOX[member]], CODEX_L2
    else:
        l1, l2 = "A Claude Code session with these tools only: " + TOOLS[member] + ".", CLAUDE_L2
    return "# Where you run\n\n" + l1 + "\n" + l2 + "\n" + S


def where_section(prompt):
    """From the `# Where you run` heading up to (not including) `# Request`, without the separating blank lines."""
    start = prompt.index("# Where you run")
    end = prompt.index("\n# Request", start)
    return prompt[start:end].rstrip("\n")


class Env:
    """Set/unset environment variables for a block and restore them after."""
    def __init__(self, **values):
        self.values, self.saved = values, {}

    def __enter__(self):
        for k, v in self.values.items():
            self.saved[k] = os.environ.get(k)
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        return self

    def __exit__(self, *a):
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


class Fixture(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="hacheong-native-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.repo = os.path.join(self.dir, "repo")
        os.makedirs(self.repo)
        subprocess.run(["git", "init", "-q"], cwd=self.repo, check=True)
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=self.repo, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=self.repo, check=True)
        with open(os.path.join(self.repo, "README.md"), "w", encoding="utf-8") as fh:
            fh.write("# x\n")
        subprocess.run(["git", "add", "-A"], cwd=self.repo, check=True)
        subprocess.run(["git", "commit", "-qm", "base"], cwd=self.repo, check=True)
        # fake host CLIs: if anything starts a host session, the marker appears
        self.bin = os.path.join(self.dir, "bin")
        os.makedirs(self.bin)
        self.marker = os.path.join(self.dir, "host-started")
        for name in ("claude", "codex"):
            p = os.path.join(self.bin, name)
            with open(p, "w") as fh:
                fh.write("#!/bin/sh\necho %s >> '%s'\nexit 1\n" % (name, self.marker))
            os.chmod(p, 0o755)

    def request(self, **extra):
        req = {"artifact-type": "chongdae/request@1", "stage": "build", "run": "run-1", "task": "T1", "role": "nitpick",
               "target": self.repo, "goal": "g", "brief": "make it", "closes": [], "contract": {}, "checks": [], "response": "./r.json"}
        req.update(extra)
        path = os.path.join(self.dir, "req-%d.json" % len(os.listdir(self.dir)))
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(req, fh, ensure_ascii=False)
        return req, path

    def prompt_only(self, member, req_path, host=None, env=None):
        response = os.path.join(self.dir, "resp-%s-%s.json" % (member.replace("/", "_"), host))
        argv = [sys.executable, os.path.join(PLUGIN, "worker.py"), "--member", member, "--request", req_path, "--response", response, "--prompt-only"]
        if host:
            argv += ["--host", host]
        e = dict(os.environ)
        e.pop("AGENT_CODEX_SANDBOX", None)
        e["PATH"] = self.bin + os.pathsep + e.get("PATH", "")
        e.update(env or {})
        done = subprocess.run(argv, cwd=self.repo, env=e, capture_output=True)
        return done, response

    def local_member(self, base, policy):
        """A project-local copy of a shipped member with its own policy.json."""
        d = os.path.join(self.repo, "hacheong", "members", base)
        shutil.copytree(os.path.join(PLUGIN, "members", base), d)
        with open(os.path.join(d, "policy.json"), "w", encoding="utf-8") as fh:
            json.dump(policy, fh)
        return d


class TestN1PromptOnlyIsNative(Fixture):
    def test_N1_every_member_every_host_prints_native_and_nothing_else_happens(self):
        _, req = self.request()
        for member in MEMBERS:
            for host in ("claude", "codex", None):
                with self.subTest(member=member, host=host):
                    done, response = self.prompt_only(member, req, host)
                    self.assertEqual(done.returncode, 0, done.stderr.decode("utf-8", "replace"))
                    self.assertFalse(os.path.exists(response), "--prompt-only wrote a response file")
                    self.assertFalse(os.path.exists(response + ".tmp"))
                    self.assertFalse(os.path.exists(self.marker), "--prompt-only started a host session")
                    self.assertEqual(where_section(done.stdout.decode("utf-8")), NATIVE)

    def test_N1_the_section_is_heading_blank_line_and_exactly_two_lines(self):
        _, req = self.request()
        done, _ = self.prompt_only("sibi", req, "codex")
        section = where_section(done.stdout.decode("utf-8"))
        lines = section.split("\n")
        self.assertEqual(lines[:2], ["# Where you run", ""])
        self.assertEqual(len(lines), 4, lines)
        self.assertEqual(lines[3], S)
        self.assertIn("printed by `worker.py --prompt-only`, which grants nothing", lines[2])


class TestN2HostDoesNotChangeThePrompt(Fixture):
    def outputs(self, member, req, env=None):
        outs = {}
        for host in ("claude", "codex", None):
            done, _ = self.prompt_only(member, req, host, env)
            self.assertEqual(done.returncode, 0, done.stderr.decode("utf-8", "replace"))
            outs[host] = done.stdout
        return outs

    def test_N2_stdout_is_byte_identical_across_hosts_for_every_member(self):
        _, req = self.request()
        for member in MEMBERS:
            with self.subTest(member=member):
                outs = self.outputs(member, req)
                self.assertEqual(outs["claude"], outs["codex"])
                self.assertEqual(outs[None], outs["codex"])
                self.assertIn(NATIVE.encode("utf-8"), outs["codex"])

    def test_N2_agent_codex_sandbox_in_the_env_changes_nothing(self):
        _, req = self.request()
        for member in ("dakdol", "sibi"):
            with self.subTest(member=member):
                plain = self.outputs(member, req)
                for sandbox in ("danger-full-access", "read-only", "workspace-write"):
                    outs = self.outputs(member, req, {"AGENT_CODEX_SANDBOX": sandbox})
                    self.assertEqual(outs["claude"], outs["codex"])
                    self.assertEqual(outs[None], outs["codex"])
                    self.assertEqual(outs["codex"], plain["codex"], "AGENT_CODEX_SANDBOX=%s changed the prompt" % sandbox)
                    self.assertNotIn(sandbox.encode("utf-8"), where_section(outs["codex"].decode("utf-8")).encode("utf-8"))

    def test_N2_a_local_policy_with_can_or_another_sandbox_changes_nothing_across_hosts(self):
        _, req = self.request()
        policies = [{"tools": "Read,Grep,Glob", "sandbox": "read-only", "can": {"network": True, "loopback": True}},
                    {"tools": "Bash,Read", "sandbox": "danger-full-access"},
                    {"tools": "Read", "sandbox": "workspace-write", "can": {"network": False, "loopback": False}}]
        for policy in policies:
            with self.subTest(policy=policy):
                shutil.rmtree(os.path.join(self.repo, "hacheong"), ignore_errors=True)
                self.local_member("sibi", policy)
                outs = self.outputs("sibi", req)
                self.assertEqual(outs["claude"], outs["codex"])
                self.assertEqual(outs[None], outs["codex"])
                self.assertEqual(where_section(outs["codex"].decode("utf-8")), NATIVE)


class TestN3NoPromisedEnvironment(Fixture):
    def test_N3_shipped_members_section_names_no_environment(self):
        _, req = self.request()
        for member in MEMBERS:
            for host in ("claude", "codex", None):
                with self.subTest(member=member, host=host):
                    done, _ = self.prompt_only(member, req, host, {"AGENT_CODEX_SANDBOX": "workspace-write"} if host == "codex" else None)
                    section = where_section(done.stdout.decode("utf-8"))
                    for phrase in FORBIDDEN + (TOOLS[member],):
                        self.assertNotIn(phrase, section)

    def test_N3_a_local_members_policy_tools_and_can_are_not_promised(self):
        _, req = self.request()
        self.local_member("dakdol", {"tools": "Read,Write,WebFetch", "sandbox": "read-only", "can": {"network": True, "loopback": True}})
        for host in ("claude", "codex"):
            with self.subTest(host=host):
                done, _ = self.prompt_only("dakdol", req, host)
                self.assertEqual(done.returncode, 0, done.stderr.decode("utf-8", "replace"))
                section = where_section(done.stdout.decode("utf-8"))
                for phrase in FORBIDDEN + ("Read,Write,WebFetch",):
                    self.assertNotIn(phrase, section)


class TestN4LackedIsKept(Fixture):
    def test_N4_section_ends_with_S_and_schema_keeps_lacked(self):
        _, req = self.request()
        for member in MEMBERS:
            for host in ("claude", "codex", None):
                with self.subTest(member=member, host=host):
                    done, _ = self.prompt_only(member, req, host)
                    out = done.stdout.decode("utf-8")
                    self.assertTrue(where_section(out).endswith("\n" + S))
                    marker = "matching this schema:\n"
                    schema, _ = json.JSONDecoder().raw_decode(out, out.index(marker) + len(marker))
                    self.assertEqual(schema["properties"]["lacked"]["items"]["enum"], ["network", "loopback"])
                    self.assertEqual(schema["properties"]["lacked"]["type"], "array")
                    self.assertIn("lacked", schema["required"])


class TestN5ContractsKept(Fixture):
    def test_N5_sections_in_order_request_and_schema_parse_equal(self):
        req, path = self.request(brief="한국어 브리프 — 트집", needs=["network"], goal="ünïcødé ✓")
        for member in MEMBERS:
            for host in ("claude", "codex", None):
                with self.subTest(member=member, host=host):
                    done, _ = self.prompt_only(member, path, host)
                    self.assertEqual(done.returncode, 0, done.stderr.decode("utf-8", "replace"))
                    out = done.stdout.decode("utf-8")
                    domain = worker.domain_for(req)
                    idx = [out.index(h) for h in ("# Who you are", "# The domain: %s" % domain, "# Where you run", "# Request", "# Answer")]
                    self.assertEqual(idx, sorted(idx))
                    self.assertEqual(len(set(idx)), 5)
                    printed, _ = json.JSONDecoder().raw_decode(out, out.index(REQUEST_LINE + "\n\n") + len(REQUEST_LINE) + 2)
                    self.assertEqual(printed, req)
                    marker = "matching this schema:\n"
                    schema, _ = json.JSONDecoder().raw_decode(out, out.index(marker) + len(marker))
                    self.assertEqual(schema, worker.load_member(member)["schema"])

    def test_N5_a_loopback_need_under_codex_prompt_only_is_still_printed(self):
        req, path = self.request(needs=["loopback"])
        for member in ("sibi", "dakdol"):
            with self.subTest(member=member):
                done, response = self.prompt_only(member, path, "codex")
                self.assertEqual(done.returncode, 0, done.stderr.decode("utf-8", "replace"))
                self.assertFalse(os.path.exists(response))
                self.assertFalse(os.path.exists(self.marker))
                out = done.stdout.decode("utf-8")
                self.assertIn("# Who you are", out)
                self.assertIn("# Answer", out)
                self.assertIn('"loopback"', out)


class TestN6SubprocessRenderingsUnchanged(Fixture):
    def setUp(self):
        super().setUp()
        env = Env(AGENT_CODEX_SANDBOX=None)
        env.__enter__()
        self.addCleanup(env.__exit__)

    def test_N6_environment_text_for_claude_and_codex(self):
        for member in MEMBERS:
            m = worker.load_member(member)
            for host in ("claude", "codex"):
                with self.subTest(member=member, host=host):
                    self.assertEqual(worker.environment_text(m, host), expected_env(member, host))

    def test_N6_assemble_carries_the_host_rendering(self):
        req, _ = self.request()
        for member in MEMBERS:
            m = worker.load_member(member, self.repo)
            for host in ("claude", "codex"):
                with self.subTest(member=member, host=host):
                    prompt, _ = worker.assemble(m, req, "code", self.repo, host)
                    self.assertEqual(where_section(prompt), expected_env(member, host))
                    self.assertNotIn(NATIVE, prompt)

    def test_N6_assemble_without_a_host_is_the_claude_form(self):
        req, _ = self.request()
        for member in MEMBERS:
            with self.subTest(member=member):
                prompt, _ = worker.assemble(worker.load_member(member), req, "code")
                self.assertEqual(where_section(prompt), expected_env(member, "claude"))

    def test_N6_default_tools_when_policy_names_none(self):
        m = worker.load_member("sibi")
        m = dict(m, policy={k: v for k, v in m["policy"].items() if k != "tools"})
        self.assertEqual(worker.environment_text(m, "claude"),
                         "# Where you run\n\nA Claude Code session with these tools only: Read,Grep,Glob.\n" + CLAUDE_L2 + "\n" + S)


class TestN7MainHandsTheHostItsRendering(Fixture):
    def setUp(self):
        super().setUp()
        env = Env(AGENT_CODEX_SANDBOX=None)
        env.__enter__()
        self.addCleanup(env.__exit__)
        saved = (worker.claude, worker.codex, list(sys.argv))

        def restore():
            worker.claude, worker.codex = saved[0], saved[1]
            sys.argv[:] = saved[2]
        self.addCleanup(restore)
        self.calls = []

        def stub(name):
            def call(prompt, member, args, target):
                self.calls.append((name, prompt, member["name"], target))
                return {"status": "done", "summary": "s", "non-claims": [], "findings": []}, ""
            return call
        worker.claude, worker.codex = stub("claude"), stub("codex")

    def test_N7_main_passes_the_hosts_rendering_never_native(self):
        _, req = self.request()
        for member in ("sibi", "dakdol"):
            for host in ("claude", "codex"):
                with self.subTest(member=member, host=host):
                    self.calls.clear()
                    response = os.path.join(self.dir, "main-%s-%s.json" % (member, host))
                    sys.argv[:] = ["worker.py", "--member", member, "--request", req, "--response", response, "--host", host]
                    with contextlib.redirect_stdout(io.StringIO()):
                        worker.main()
                    self.assertEqual([c[0] for c in self.calls], [host])
                    prompt = self.calls[0][1]
                    self.assertEqual(where_section(prompt), expected_env(member, host))
                    self.assertNotIn(NATIVE, prompt)
                    self.assertNotIn("printed by `worker.py --prompt-only`", prompt)
                    self.assertTrue(os.path.exists(response))


if __name__ == "__main__":
    unittest.main()
