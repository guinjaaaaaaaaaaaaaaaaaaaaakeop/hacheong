"""Self-check for hacheong: members load and assemble, the host stream parses into an answer and nothing short of a real
one is `done`, each validator fires on a recorded case, project-local members shadow the plugin's, `new` scaffolds something
`check` refuses until it is written.

  python3 test_hacheong.py
"""
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import worker as w  # noqa: E402
import hacheong as h  # noqa: E402

REQUEST = {"artifact-type": "chongdae/request@1", "stage": "build", "run": "run-1", "task": "T1", "role": "implementer", "target": ".",
           "goal": "g", "brief": "make it", "closes": ["Q-add"], "contract": {"Q-add": "## Q-add\n\n`add` appends."},
           "checks": [["python3", "-m", "unittest", "tests/test_x.py", "-k", "Q_add"]], "response": "./r.json"}
GOOD = {"status": "done", "summary": "added", "verified": [{"check": "python3 -m unittest tests/test_x.py -k Q_add", "exit": 0}], "decisions": [], "non-claims": []}


def stream(*events):
    return "\n".join(json.dumps(e) for e in events) + "\n"


def claude_stream(*tool_uses, result=None):
    evs = [{"type": "system", "subtype": "init", "model": "claude-t", "session_id": "s1"}]
    for name, inp in tool_uses:
        evs.append({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": name, "input": inp}]}})
    evs.append({"type": "result", "num_turns": len(tool_uses) + 1, "total_cost_usd": 0.01, "session_id": "s1", "structured_output": result or GOOD})
    return stream(*evs)


class Repo:
    """A temp git repo with one committed file."""
    def __enter__(self):
        self.dir = tempfile.mkdtemp(prefix="hacheong-t-")
        subprocess.run(["git", "init", "-q"], cwd=self.dir, check=True)
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=self.dir); subprocess.run(["git", "config", "user.name", "t"], cwd=self.dir)
        self.write("README.md", "# x\n\nrun `python3 app.py`\n")
        subprocess.run(["git", "add", "-A"], cwd=self.dir); subprocess.run(["git", "commit", "-qm", "base"], cwd=self.dir)
        return self

    def write(self, rel, text):
        p = os.path.join(self.dir, rel); os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(text)

    def __exit__(self, *a):
        shutil.rmtree(self.dir, ignore_errors=True)


class Skip(Exception):
    """Raised by a test that cannot run on this host; the runner reports it as SKIP, never as PASS."""


def test_every_shipped_member_loads_and_the_roster_matches_the_roles():
    roles = h.declared_roles()
    assert roles == {"build": "dakdol", "quibble": "sibi", "nitpick": "teujip", "newbie": "chojja"}, roles
    for m in h.members_in(os.path.join(HERE, "members") and __import__("pathlib").Path(HERE) / "members"):
        mem = w.load_member(m)
        assert mem["schema"]["required"][:3] == ["status", "summary", "non-claims"] or set(("status", "summary", "non-claims")) <= set(mem["schema"]["required"]), m
        assert set(mem["policy"]) <= w.POLICY_KEYS
    assert h.problems_of(__import__("pathlib").Path(HERE) / "members", roles) == []


def test_the_prompt_is_role_then_domain_section_then_request():
    mem = w.load_member("sibi")
    prompt, dpath = w.assemble(mem, REQUEST, "code")
    assert prompt.index("# Who you are") < prompt.index("시비 (sibi)") < prompt.index("# The domain: code") < prompt.index("## sibi") < prompt.index("# Request")
    assert "## dakdol" not in prompt and "## teujip" not in prompt, "only this member's domain section"
    assert dpath.endswith("domains/code/DOMAIN.md")
    prompt, dpath = w.assemble(mem, REQUEST, "design")
    assert dpath is None and "No domain text is available for 'design'" in prompt
    assert w.domain_for(REQUEST) == "code" and w.domain_for(dict(REQUEST, produces="plan/document@1")) == "plan"
    assert w.domain_for(dict(REQUEST, produces="chongdae/plan@1")) == "code" and w.domain_for(dict(REQUEST, domain="design")) == "design"
    assert w.domain_for(REQUEST, "plan") == "plan"
    # the newbie's material is the domain's to say: in a plan there is no program to try, and form is the quibbler's
    prompt, _ = w.assemble(w.load_member("chojja"), REQUEST, "plan")
    assert "the domain below says what that is" in prompt and "there is no program or README to try here" in prompt
    assert "is the quibbler's to check, not yours" in prompt
    # a plan still deciding what to build: a findings section carries sources, not acceptance sentences
    prompt, _ = w.assemble(mem, REQUEST, "plan")
    assert "findings:" in prompt and "a claim with no source behind it" in prompt and "has no slices yet" in prompt
    # where the session runs is said up front: a Codex builder learns before it starts that there is no network and .git is read-only
    prompt, _ = w.assemble(w.load_member("dakdol"), REQUEST, "code", host="codex")
    assert "no network" in prompt and "`.git` is read-only" in prompt and "stop with `status: blocked` and name it" in prompt
    assert prompt.index("# Where you run") < prompt.index("# Request")
    prompt, _ = w.assemble(w.load_member("sibi"), REQUEST, "code", host="claude")
    assert "with these tools only: Read,Grep,Glob" in prompt
    # the builder runs what decides its change while it works, the full checks once at the end
    assert "not the whole suite each time" in w.load_member("dakdol")["role"]


def test_the_envelope_is_added_to_every_schema_and_bad_members_are_refused():
    d = tempfile.mkdtemp(prefix="hacheong-m-")
    try:
        m = os.path.join(d, "mine"); os.makedirs(m)
        open(os.path.join(m, "ROLE.md"), "w").write("# mine\n\nyou are.\n")
        open(os.path.join(m, "answer.json"), "w").write(json.dumps({"properties": {"findings": {"type": "array"}}, "required": ["findings"]}))
        mem = w.load_member(m)
        assert mem["schema"]["type"] == "object" and mem["schema"]["additionalProperties"] is False
        assert set(mem["schema"]["required"]) == {"findings", "status", "summary", "non-claims"} and mem["schema"]["properties"]["status"]["enum"] == ["done", "blocked", "failed"]
        open(os.path.join(m, "policy.json"), "w").write(json.dumps({"tools": "Read", "validate": ["telepathy"]}))
        try:
            w.load_member(m); assert False
        except SystemExit as err:
            assert "unknown validators ['telepathy']" in str(err)
        open(os.path.join(m, "policy.json"), "w").write(json.dumps({"colour": "red"}))
        try:
            w.load_member(m); assert False
        except SystemExit as err:
            assert "unknown keys ['colour']" in str(err)
        try:
            w.load_member("nobody"); assert False
        except SystemExit as err:
            assert "no member 'nobody'" in str(err) and "chojja, dakdol, sibi, teujip" in str(err)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_a_projects_own_member_and_domain_shadow_the_plugins():
    with Repo() as r:
        r.write("hacheong/members/sibi/ROLE.md", "# the project's own sibi\n\nquieter.\n")
        r.write("hacheong/members/sibi/answer.json", json.dumps({"properties": {"findings": {"type": "array"}}}))
        r.write("hacheong/members/sibi/policy.json", json.dumps({"tools": "Read"}))
        r.write("hacheong/domains/code/DOMAIN.md", "the project's code domain\n\n## sibi\n\nmind the house style\n")
        mem = w.load_member("sibi", r.dir)
        assert "quieter" in mem["role"] and mem["policy"] == {"tools": "Read"}
        prompt, dpath = w.assemble(mem, REQUEST, "code", r.dir)
        assert "mind the house style" in prompt and dpath.startswith(r.dir)
        assert "quieter" in w.load_member("./hacheong/members/sibi", r.dir)["role"], "a path with a slash is taken as is"
        assert "picks a quarrel" in w.load_member("sibi")["role"], "without a target, the plugin's"


def test_the_host_stream_parses_and_nothing_short_of_an_answer_is_done():
    assert w.parse_claude(0, stream({"type": "result", "structured_output": GOOD}), "") == GOOD
    out = w.parse_claude(0, stream({"type": "result", "result": json.dumps(GOOD)}), "")
    assert out["status"] == "done"
    assert w.parse_claude(0, stream({"type": "result", "result": "I did it."}), "")["status"] == "failed"
    assert w.parse_claude(1, "", "boom")["status"] == "failed"
    assert w.parse_claude(0, stream({"type": "result", "is_error": True, "subtype": "error_max_turns"}), "")["status"] == "failed"
    assert w.parse_claude(0, stream({"type": "result", "structured_output": {"status": "maybe"}}), "")["status"] == "failed"
    rec = w.worker_record(claude_stream(), "/tmp/hacheong-x/T1.response.json", "claude-code")
    assert rec["model"] == "claude-t" and rec["turns"] == 1 and rec["transcript"] == "T1.response.transcript.jsonl"
    shutil.rmtree("/tmp/hacheong-x", ignore_errors=True)


def test_validators_fire_on_recorded_cases():
    with Repo() as r:
        before = w.tree_state(r.dir)
        # quotes-required: a finding without a quote is an opinion
        sibi = w.load_member("sibi")
        out = {"status": "done", "summary": "", "non-claims": [], "findings": [{"kind": "undecided", "where": "Q-add", "quote": "", "why": "x"}]}
        out = w.validate(out, sibi, REQUEST, r.dir, claude_stream(result=out), "claude-code", before)
        assert out["status"] == "failed" and out["validation"]["failed"] == ["quotes-required"] and "findings[0] carry no quote" in out["non-claims"][0], out
        # no-tree-changes: sibi may not touch the project
        r.write("app.py", "x = 1\n")
        out = w.validate({"status": "done", "summary": "", "non-claims": [], "findings": []}, sibi, REQUEST, r.dir, "", "claude-code", before)
        assert out["status"] == "failed" and "the tree changed (app.py)" in out["non-claims"][0], out
        os.remove(os.path.join(r.dir, "app.py"))
        # checks-ran: a check claimed verified must appear in the transcript; python vs python3 is not a difference
        dakdol = w.load_member("dakdol")
        ran = claude_stream(("Bash", {"command": "python -m unittest tests/test_x.py -k Q_add"}))
        assert w.validate(dict(GOOD), dakdol, REQUEST, r.dir, ran, "claude-code", before)["status"] == "done"
        out = w.validate(dict(GOOD), dakdol, REQUEST, r.dir, claude_stream(("Bash", {"command": "ls"})), "claude-code", before)
        assert out["status"] == "failed" and "claimed verified but no such command" in out["non-claims"][0], out
        # a remark after the command ("(8 tests, OK)") cost a whole rebuild when seen live: it is not part of the command
        remarked = dict(GOOD, verified=[{"check": "python3 -m unittest tests/test_x.py -k Q_add (8 tests, OK)", "exit": 0}])
        assert w.validate(remarked, dakdol, REQUEST, r.dir, ran, "claude-code", before)["status"] == "done"
        # the worker's own transcript lands in the run's record inside the target: not a tree change
        r.write(".chongdae/run-1/T1.quibble.response.transcript.jsonl", "{}\n")
        assert w.validate({"status": "done", "summary": "", "non-claims": [], "findings": []}, sibi, REQUEST, r.dir, "", "claude-code", before)["status"] == "done"
        # codex transcripts: command_execution items
        codex = stream({"type": "item.completed", "item": {"type": "command_execution", "command": "/bin/zsh -lc 'python3 -m unittest tests/test_x.py -k Q_add'"}})
        assert w.validate(dict(GOOD), dakdol, REQUEST, r.dir, codex, "codex", before)["status"] == "done"
        # the same argv, quoted as it ran (zsh would glob the pattern) and reported unquoted: a true claim (seen live: failed three times)
        quoted = stream({"type": "item.completed", "item": {"type": "command_execution", "command": "/bin/zsh -lc \"python3 -m unittest discover -s tests -p 'test_s[12].py'\""}})
        claim = dict(GOOD, verified=[{"check": "python3 -m unittest discover -s tests -p test_s[12].py", "exit": 0}])
        assert w.validate(claim, dakdol, REQUEST, r.dir, quoted, "codex", before)["status"] == "done"
        # ...while a tidied rewrite of what ran is still not what ran
        tidied = dict(GOOD, verified=[{"check": "python3 -m unittest discover -s tests -p test_s3.py", "exit": 0}])
        assert w.validate(tidied, dakdol, REQUEST, r.dir, quoted, "codex", before)["status"] == "failed"
        # red-before-build and only-tests-touched: teujip's tests must fail now, and only tests may change
        teujip = w.load_member("teujip")
        r.write("tests/test_x.py", "import unittest\nclass T(unittest.TestCase):\n    def test_Q_add_appends(self):\n        import app\n")
        before2 = w.tree_state(r.dir)
        ans = {"status": "done", "summary": "", "non-claims": [], "tests": ["tests/test_x.py"], "covers": [{"section": "Q-add", "tests": ["test_Q_add_appends"]}]}
        assert w.validate(json.loads(json.dumps(ans)), teujip, REQUEST, r.dir, "", "claude-code", before)["status"] == "done", "red: app is missing"
        r.write("tests/test_x.py", "import unittest\nclass T(unittest.TestCase):\n    def test_Q_add_appends(self):\n        pass\n")
        out = w.validate(json.loads(json.dumps(ans)), teujip, REQUEST, r.dir, "", "claude-code", before)
        assert out["status"] == "failed" and "passes before the build" in out["non-claims"][0], out
        # amending tests the build disputed: the build already stands, so corrected tests may pass — the waiver is the request's
        amend = dict(REQUEST, amending=[{"test": "tests/test_x.py", "contract_quote": "x", "why": "y"}])
        assert w.validate(json.loads(json.dumps(ans)), teujip, amend, r.dir, "", "claude-code", before)["status"] == "done"
        r.write("tests/test_x.py", "import unittest\nclass T(unittest.TestCase):\n    def test_Q_add_appends(self):\n        self.fail('not built')\n")
        r.write("app.py", "stub = 1\n")
        out = w.validate(json.loads(json.dumps(ans)), teujip, REQUEST, r.dir, "", "claude-code", before)
        assert out["status"] == "failed" and "changed outside the tests it declared: app.py" in " ".join(out["non-claims"]), out
        os.remove(os.path.join(r.dir, "app.py"))
        # readme-only: a newbie who opened source is tainted — Read tool or a shell read alike
        chojja = w.load_member("chojja")
        clean = {"status": "done", "summary": "", "non-claims": [], "tried": [], "findings": []}
        ok = claude_stream(("Read", {"file_path": r.dir + "/README.md"}), ("Bash", {"command": "cd $(mktemp -d) && python3 %s/app.py --help" % r.dir}), result=clean)
        assert w.validate(dict(clean), chojja, REQUEST, r.dir, ok, "claude-code", w.tree_state(r.dir))["status"] == "done"
        r.write("app.py", "print('hi')\n")   # a project file exists to be peeked at
        peek = claude_stream(("Read", {"file_path": r.dir + "/app.py"}), result=clean)
        out = w.validate(dict(clean), chojja, REQUEST, r.dir, peek, "claude-code", w.tree_state(r.dir))
        assert out["status"] == "failed" and "read what a newbie would not" in out["non-claims"][0] and "app.py" in out["non-claims"][0], out
        peek2 = claude_stream(("Bash", {"command": "cat tests/test_x.py"}), result=clean)
        assert w.validate(dict(clean), chojja, REQUEST, r.dir, peek2, "claude-code", w.tree_state(r.dir))["status"] == "failed"
        # running the program is not reading it, and a data file in the scratch dir is not source — the live chojja round was
        # flagged for `python3 <target>/todo.py` sharing a command line with `cat todo.json`
        ran = claude_stream(("Bash", {"command": "cd $(mktemp -d) && python3 %s/app.py add x; cat todo.json; python3 %s/app.py list | head -3" % (r.dir, r.dir)}), result=clean)
        out = w.validate(dict(clean), chojja, REQUEST, r.dir, ran, "claude-code", w.tree_state(r.dir))
        assert out["status"] == "done", out
        assert w.validate(dict(clean), chojja, REQUEST, r.dir, claude_stream(("Bash", {"command": "head -5 %s/app.py" % r.dir}), result=clean), "claude-code", w.tree_state(r.dir))["status"] == "failed"
        # a site's generated page is the product: reading it is a visitor's read in the site domain, peeking in the code domain
        r.write("docs/index.html", "<p>hi</p>\n")
        page = claude_stream(("Read", {"file_path": r.dir + "/docs/index.html"}), result=clean)
        assert w.validate(dict(clean), chojja, dict(REQUEST, domain="site"), r.dir, page, "claude-code", w.tree_state(r.dir))["status"] == "done"
        assert w.validate(dict(clean), chojja, REQUEST, r.dir, page, "claude-code", w.tree_state(r.dir))["status"] == "failed"
        os.remove(os.path.join(r.dir, "docs", "index.html"))
        os.remove(os.path.join(r.dir, "app.py"))


def test_tests_kept_refuses_a_build_that_changed_the_contracts_tests_even_back_to_head():
    with Repo() as r:
        r.write("tests/test_x.py", "# first version\n")
        subprocess.run(["git", "add", "-A"], cwd=r.dir); subprocess.run(["git", "commit", "-qm", "tests"], cwd=r.dir)
        r.write("tests/test_x.py", "# the contract's newest version, not committed\n")
        dakdol = w.load_member("dakdol")
        request = dict(REQUEST, tests=["tests/test_x.py"])
        ran = claude_stream(("Bash", {"command": "python -m unittest tests/test_x.py -k Q_add"}))
        before = w.tree_state(r.dir)
        r.write("app.py", "x = 1\n")   # the build itself: fine
        assert w.validate(json.loads(json.dumps(GOOD)), dakdol, request, r.dir, ran, "claude-code", before)["status"] == "done"
        subprocess.run(["git", "checkout", "--", "tests/test_x.py"], cwd=r.dir, check=True)   # "restored" from HEAD
        out = w.validate(json.loads(json.dumps(GOOD)), dakdol, request, r.dir, ran, "claude-code", before)
        assert out["status"] == "failed" and "tests-kept" in out["validation"]["failed"] and "tests/test_x.py" in " ".join(out["non-claims"]), out
        # a path list given as one string is one path that is not there: nothing was kept
        out = w.validate(json.loads(json.dumps(GOOD)), dakdol, dict(REQUEST, tests=["tests/test_x.py tests/test_y.py"]), r.dir, ran, "claude-code", w.tree_state(r.dir))
        assert out["status"] == "failed" and "are not in the tree" in " ".join(out["non-claims"]), out


def test_new_scaffolds_a_member_that_check_refuses_until_written():
    with Repo() as r:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            assert h.main(["new", "grump", "--target", r.dir]) == 0
        d = os.path.join(r.dir, "hacheong", "members", "grump")
        assert os.path.exists(os.path.join(d, "ROLE.md")) and "scaffolded grump in the project's" in out.getvalue()
        probs = h.problems_of(__import__("pathlib").Path(r.dir) / "hacheong" / "members")
        assert any("template placeholders" in p for p in probs) and any("template kinds" in p for p in probs), probs
        r.write("hacheong/members/grump/ROLE.md", "# grump\n\nYou grumble about names.\n")
        r.write("hacheong/members/grump/answer.json", json.dumps({"required": ["findings"], "properties": {"findings": {"type": "array", "items": {"type": "object", "properties": {"kind": {"enum": ["bad-name"]}, "quote": {"type": "string"}}}}}}))
        assert h.problems_of(__import__("pathlib").Path(r.dir) / "hacheong" / "members") == []
        with contextlib.redirect_stdout(io.StringIO()):
            assert h.main(["check", "--target", r.dir]) == 0
        # a validator that names a field the schema lacks is refused
        r.write("hacheong/members/grump/policy.json", json.dumps({"validate": ["red-before-build"]}))
        probs = h.problems_of(__import__("pathlib").Path(r.dir) / "hacheong" / "members")
        assert any("needs a `tests` field" in p for p in probs), probs


def test_prompt_only_prints_the_prompt_and_the_schema_without_a_host():
    with Repo() as r:
        req = os.path.join(r.dir, "req.json")
        with open(req, "w") as fh:
            json.dump(dict(REQUEST, target=r.dir), fh)
        done = subprocess.run([sys.executable, os.path.join(HERE, "worker.py"), "--member", "chojja", "--request", req, "--response", os.path.join(r.dir, "r.json"), "--prompt-only"],
                              capture_output=True, text=True, encoding="utf-8")
        assert done.returncode == 0 and "초짜 (chojja)" in done.stdout and "## chojja" in done.stdout and '"tried"' in done.stdout and "# Answer" in done.stdout, done.stdout[-500:] + done.stderr
        assert not os.path.exists(os.path.join(r.dir, "r.json"))
        done = subprocess.run([sys.executable, os.path.join(HERE, "worker.py"), "--member", "chojja", "--request", os.path.join(r.dir, "README.md"), "--response", "x"], capture_output=True, text=True)
        assert done.returncode != 0


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("PASS", name)
            except Skip as why:
                print("SKIP", name, "--", why)
            except (Exception, SystemExit) as err:   # a self-check that dies between tests lies by omission
                failed += 1
                print("FAIL", name, "--", "%s: %s" % (type(err).__name__, err))
    print("all passed" if not failed else "%d failed" % failed)
    sys.exit(1 if failed else 0)


def test_explanation_kept_refuses_a_refactoring_that_dropped_its_words():
    """A site's split of build.py into five modules lost eleven docstrings and fifteen comments; the checks passed, the eyes
    accepted, a second task put them back. In the refactor domain the runner compares the project's Python inventory with
    HEAD — public names, docstrings, comment lines — and refuses an answer where any of them shrank. Outside that domain a
    build may delete; the validator stays quiet."""
    with Repo() as r:
        r.write("app.py", '"""The app."""\n\n\ndef add(store, text):\n    """Append one item."""\n    # the id is the position\n    return len(store) + 1\n\n\ndef _helper():\n    return 0\n')
        subprocess.run(["git", "add", "-A"], cwd=r.dir); subprocess.run(["git", "commit", "-qm", "before the refactoring"], cwd=r.dir)
        dakdol = w.load_member("dakdol")
        refactor = dict(REQUEST, domain="refactor")
        ran = claude_stream(("Bash", {"command": "python3 -m unittest tests/test_x.py -k Q_add"}))
        # moved with its words: fine (the private helper may go)
        os.remove(os.path.join(r.dir, "app.py"))
        r.write("core/ops.py", '"""The app."""\n\n\ndef add(store, text):\n    """Append one item."""\n    # the id is the position\n    return len(store) + 1\n')
        assert w.validate(dict(GOOD), dakdol, refactor, r.dir, ran, "claude-code", None)["status"] == "done"
        # moved without its docstring and comment: refused, saying what shrank
        r.write("core/ops.py", '"""The app."""\n\n\ndef add(store, text):\n    return len(store) + 1\n')
        out = w.validate(dict(GOOD), dakdol, refactor, r.dir, ran, "claude-code", None)
        assert out["status"] == "failed" and out["validation"]["failed"] == ["explanation-kept"], out
        assert "docstrings 2 -> 1" in out["non-claims"][0] and "comment lines 1 -> 0" in out["non-claims"][0], out["non-claims"]
        # a public name gone: refused too
        r.write("core/ops.py", '"""The app."""\n\n\ndef append(store, text):\n    """Append one item."""\n    # the id is the position\n    return len(store) + 1\n')
        out = w.validate(dict(GOOD), dakdol, refactor, r.dir, ran, "claude-code", None)
        assert out["status"] == "failed" and "public names gone: add" in out["non-claims"][0], out
        # the same tree in the code domain: a build may delete; nothing said
        assert w.validate(dict(GOOD), dakdol, REQUEST, r.dir, ran, "claude-code", None)["status"] == "done"


def test_the_tree_checks_leave_out_the_records_the_lock_declares():
    """tree_state and the refactor inventory skipped `.chongdae/ .mangsang/ .dwitbuk/` by name; now the lock's `record-paths`
    says which paths are records (each plugin declares its own), and without a lock the old names stand."""
    with Repo() as r:
        assert w.record_paths(r.dir) == (".chongdae/", ".dwitbuk/", ".mangsang/", "hunsu", "reviews/"), w.record_paths(r.dir)
        r.write("hunsu.lock.json", json.dumps({"record-paths": {"alpha": [".alpha/"], "beta": []}}))
        assert w.record_paths(r.dir) == (".alpha/", ".chongdae/", "hunsu"), w.record_paths(r.dir)
        r.write(".alpha/state.json", "{}")
        r.write("app.py", "x = 1\n")
        state = w.tree_state(r.dir)
        assert "app.py" in state and not any(k.startswith(".alpha/") for k in state), state
        r.write(".alpha/mod.py", "def hidden():\n    return 1\n")
        names, _, _ = w.inventory(r.dir, at_head=False)
        assert "hidden" not in names, names
