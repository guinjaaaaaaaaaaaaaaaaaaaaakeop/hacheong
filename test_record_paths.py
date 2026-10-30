"""The runner's record exclusion: exact record files, record directories at a path boundary, anchored at the project root,
the same rule for tree_state, the refactor inventory and the validators that read them (R1-R7).

  python3 -m unittest test_record_paths.py
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
import worker  # noqa: E402

ENV = ("hunsu.json", "hunsu.lock.json", "hunsu-judgments.json", "hunsu-conflicts.md", "hunsu.local.json")
NO_LOCK = (".chongdae/", ".dwitbuk/", ".mangsang/", "hunsu-conflicts.md", "hunsu-judgments.json", "hunsu.json", "hunsu.local.json",
           "hunsu.lock.json", "reviews/")
ALPHA = (".alpha/", ".chongdae/", "hunsu-conflicts.md", "hunsu-judgments.json", "hunsu.json", "hunsu.local.json", "hunsu.lock.json")
# a lock that declares directories, a nested directory and exact files (one of them inside a dot-directory)
DECLARED = {"record-paths": {"one": ["reviews/", "docs/rec/", "notes.rec"], "two": ["gen_record.py", ".tool/gen_record.py"]}}

REQUEST = {"artifact-type": "chongdae/request@1", "stage": "build", "run": "run-1", "task": "T1", "role": "implementer", "target": ".",
           "goal": "g", "brief": "make it", "closes": ["Q-add"], "contract": {"Q-add": "## Q-add\n\n`add` appends."},
           "checks": [["python3", "-m", "unittest", "tests/test_x.py", "-k", "Q_add"]], "response": "./r.json"}
RED_TEST = "import unittest\nclass T(unittest.TestCase):\n    def test_Q_add_appends(self):\n        self.fail('not built')\n"
TEUJIP_ANSWER = {"status": "done", "summary": "", "non-claims": [], "tests": ["tests/test_x.py"],
                 "covers": [{"section": "Q-add", "tests": ["test_Q_add_appends"]}]}
QUOTE = "only-tests-touched: changed outside the tests it declared: hunsu_helper.py"


def fresh(obj):
    return json.loads(json.dumps(obj))


def claude_stream(*tool_uses, result=None):
    evs = [{"type": "system", "subtype": "init", "model": "claude-t", "session_id": "s1"}]
    for name, inp in tool_uses:
        evs.append({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": name, "input": inp}]}})
    evs.append({"type": "result", "num_turns": len(tool_uses) + 1, "total_cost_usd": 0.01, "session_id": "s1", "structured_output": result or {}})
    return "\n".join(json.dumps(e) for e in evs) + "\n"


class RepoCase(unittest.TestCase):
    """Each test gets a temporary git repository with one committed README, removed afterwards."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="hacheong-rec-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.git("init", "-q")
        self.git("config", "user.email", "t@t")
        self.git("config", "user.name", "t")
        self.write("README.md", "# x\n")
        self.commit("base")

    def git(self, *args):
        subprocess.run(["git", *args], cwd=self.dir, check=True, capture_output=True)

    def commit(self, message):
        self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", message)

    def write(self, rel, text):
        p = os.path.join(self.dir, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(text)

    def lock(self, obj):
        self.write("hunsu.lock.json", obj if isinstance(obj, str) else json.dumps(obj))

    def state(self):
        s = worker.tree_state(self.dir)
        self.assertIsInstance(s, dict, "tree_state of a git repository is a mapping")
        return s

    def names(self, at_head):
        inv = worker.inventory(self.dir, at_head=at_head)
        return inv[0]

    def assertVisible(self, rel, state):
        self.assertIn(rel, state, "%s is a project file, not a record: tree_state must show it" % rel)

    def assertHidden(self, rel, state):
        self.assertNotIn(rel, state, "%s is a record: tree_state must leave it out" % rel)


class R1RecordPaths(RepoCase):
    def test_R1_no_lock_is_chongdae_env_and_the_fallback_exactly(self):
        got = worker.record_paths(self.dir)
        self.assertIsInstance(got, tuple)
        self.assertEqual(got, NO_LOCK)

    def test_R1_lock_with_record_paths_is_chongdae_env_and_the_declared_union_exactly(self):
        self.lock({"record-paths": {"alpha": [".alpha/"], "beta": []}})
        got = worker.record_paths(self.dir)
        self.assertIsInstance(got, tuple)
        self.assertEqual(got, ALPHA)

    def test_R1_never_contains_a_bare_hunsu(self):
        self.assertNotIn("hunsu", worker.record_paths(self.dir))
        self.lock({"record-paths": {"alpha": [".alpha/"]}})
        self.assertNotIn("hunsu", worker.record_paths(self.dir))

    def test_R1_unreadable_lock_falls_back(self):
        self.lock("{not json")
        self.assertEqual(worker.record_paths(self.dir), NO_LOCK)

    def test_R1_lock_without_a_record_paths_mapping_falls_back(self):
        for lock in ({}, {"record-paths": [".alpha/"]}, {"record-paths": ".alpha/"}, {"record-paths": None}, {"plugins": {}}):
            with self.subTest(lock=lock):
                self.lock(lock)
                self.assertEqual(worker.record_paths(self.dir), NO_LOCK)

    def test_R1_declared_paths_are_unioned_sorted_and_unique(self):
        self.lock({"record-paths": {"z": ["zz/", "notes.rec", ".chongdae/"], "a": ["notes.rec", "hunsu.json", "aa/"], "e": []}})
        got = worker.record_paths(self.dir)
        self.assertIsInstance(got, tuple)
        self.assertEqual(got, tuple(sorted(set(got))), "sorted, each entry once")
        self.assertEqual(got, (".chongdae/", "aa/", "hunsu-conflicts.md", "hunsu-judgments.json", "hunsu.json", "hunsu.local.json",
                               "hunsu.lock.json", "notes.rec", "zz/"))


class R2Rule(RepoCase):
    def setUp(self):
        super().setUp()
        self.lock(DECLARED)

    def test_R2_a_directory_record_covers_everything_under_it_at_any_depth(self):
        for rel in ("reviews/a.json", "reviews/x/y.json", "reviews/x/y/z.py", "docs/rec/x.json"):
            self.write(rel, "{}\n")
        s = self.state()
        for rel in ("reviews/a.json", "reviews/x/y.json", "reviews/x/y/z.py", "docs/rec/x.json"):
            self.assertHidden(rel, s)

    def test_R2_a_directory_record_never_covers_a_prefix_sibling(self):
        sibs = ("reviews-old/a.json", "reviewsx/a.py", "reviews.md", "docs/record/x.json", "docs/rec.md")
        for rel in sibs:
            self.write(rel, "x\n")
        s = self.state()
        for rel in sibs:
            self.assertVisible(rel, s)

    def test_R2_a_directory_record_is_anchored_at_the_root(self):
        deeper = ("docs/reviews/a.json", "app/reviews/models.py", "x/docs/rec/x.json")
        for rel in deeper:
            self.write(rel, "x\n")
        s = self.state()
        for rel in deeper:
            self.assertVisible(rel, s)

    def test_R2_a_file_record_covers_exactly_that_path(self):
        self.write("notes.rec", "r\n")
        self.write("hunsu.json", "{}\n")
        self.write("gen_record.py", "def rec_gen():\n    return 1\n")
        s = self.state()
        for rel in ("notes.rec", "hunsu.json", "gen_record.py"):
            self.assertHidden(rel, s)

    def test_R2_a_file_record_never_covers_a_prefix_neighbour(self):
        neighbours = ("hunsu.json.bak", "hunsu.jsonx", "notes.rec.bak", "notes.recx", "gen_record.py.orig", "gen_record_tool.py")
        for rel in neighbours:
            self.write(rel, "x\n")
        s = self.state()
        for rel in neighbours:
            self.assertVisible(rel, s)

    def test_R2_a_file_record_is_anchored_at_the_root(self):
        for rel in ("sub/hunsu.json", "sub/notes.rec", "lib/gen_record.py"):
            self.write(rel, "x\n")
        s = self.state()
        for rel in ("sub/hunsu.json", "sub/notes.rec", "lib/gen_record.py"):
            self.assertVisible(rel, s)

    def test_R2_the_same_rule_holds_in_the_inventory(self):
        files = {"reviewsx/a.py": "rec_reviewsx", "docs/record/x.py": "rec_docs_record", "app/reviews/models.py": "rec_app_reviews",
                 "reviews/a.py": "rec_reviews", "docs/rec/x.py": "rec_docs_rec", "gen_record.py": "rec_gen",
                 "gen_record_tool.py": "rec_gen_tool"}
        for rel, name in files.items():
            self.write(rel, "def %s():\n    return 1\n" % name)
        names = self.names(False)
        for name in ("rec_reviewsx", "rec_docs_record", "rec_app_reviews", "rec_gen_tool"):
            self.assertIn(name, names, "%s's file is not a record" % name)
        for name in ("rec_reviews", "rec_docs_rec", "rec_gen"):
            self.assertNotIn(name, names, "%s's file is a record" % name)


class R3TreeState(RepoCase):
    SOURCES = ("hunsu.py", "hunsu_helper.py", "hunsu-notes.md")

    def test_R3_hunsu_named_sources_appear_when_created(self):
        for rel in self.SOURCES:
            self.write(rel, "x = 1\n")
        s = self.state()
        for rel in self.SOURCES:
            self.assertVisible(rel, s)

    def test_R3_hunsu_named_sources_appear_when_changed(self):
        for rel in self.SOURCES:
            self.write(rel, "x = 1\n")
        self.commit("sources")
        before = self.state()
        for rel in self.SOURCES:
            self.write(rel, "x = 2\n")
        after = self.state()
        for rel in self.SOURCES:
            self.assertVisible(rel, after)
            self.assertNotEqual(before.get(rel), after.get(rel), "%s changed and tree_state must say so" % rel)

    def test_R3_prefix_neighbours_and_deeper_names_appear_with_a_lock(self):
        self.lock(DECLARED)
        shown = ("hunsu.json.bak", "notes.recx", "reviews-old/a.json", "docs/rec.md", "docs/reviews/a.json", "sub/hunsu.json",
                 "hunsu.py", "hunsu_helper.py", "hunsu-notes.md")
        for rel in shown:
            self.write(rel, "x\n")
        s = self.state()
        for rel in shown:
            self.assertVisible(rel, s)

    def test_R3_prefix_neighbours_of_the_fallback_appear_without_a_lock(self):
        shown = ("reviews-old/a.json", "reviews.md", ".chongdae-notes/a.md", ".dwitbukx", "hunsu.json.bak", "hunsu.lock.json.orig")
        for rel in shown:
            self.write(rel, "x\n")
        s = self.state()
        for rel in shown:
            self.assertVisible(rel, s)

    def test_R3_env_files_chongdae_and_declared_records_stay_out(self):
        self.lock(DECLARED)
        hidden = ENV + (".chongdae/run-1/state.json", "reviews/a.json", "docs/rec/x.json", "notes.rec", "gen_record.py", ".tool/gen_record.py")
        for rel in hidden:
            if rel != "hunsu.lock.json":
                self.write(rel, "{}\n")
        self.write("app.py", "x = 1\n")
        s = self.state()
        self.assertVisible("app.py", s)
        for rel in hidden:
            self.assertHidden(rel, s)
        self.assertFalse([k for k in s if k == "hunsu" or k.startswith(".chongdae/")], s)

    def test_R3_the_existing_skips_stay(self):
        for rel in ("__pycache__/m.cpython-312.pyc", "pkg/__pycache__/n.pyc", "mod.pyc", ".DS_Store", "pkg/.DS_Store"):
            self.write(rel, "x\n")
        self.write("hunsu.py", "x = 1\n")
        s = self.state()
        self.assertVisible("hunsu.py", s)
        self.assertFalse([k for k in s if "__pycache__" in k or k.endswith(".pyc") or k.endswith(".DS_Store")], s)


class R4Inventory(RepoCase):
    def populate(self):
        self.lock(DECLARED)
        files = {"gen_record.py": "rec_exact", ".tool/gen_record.py": "rec_dot_exact", "gen_record_tool.py": "rec_neighbour",
                 "hunsu.py": "rec_hunsu", "hunsu_helper.py": "rec_hunsu_helper", "app/reviews/models.py": "rec_app_reviews",
                 "reviews/gen.py": "rec_reviews", ".tool/other.py": "rec_dot_other"}
        for rel, name in files.items():
            self.write(rel, '"""%s."""\n\n\ndef %s():\n    # %s\n    return 1\n' % (name, name, name))

    def check(self, at_head):
        names = self.names(at_head)
        for name in ("rec_neighbour", "rec_hunsu", "rec_hunsu_helper", "rec_app_reviews"):
            self.assertIn(name, names, "at_head=%s: %s's file is not a record and is counted" % (at_head, name))
        for name in ("rec_exact", "rec_dot_exact", "rec_reviews"):
            self.assertNotIn(name, names, "at_head=%s: %s's file is a declared record and is not counted" % (at_head, name))

    def test_R4_working_tree_counts_neighbours_and_skips_exact_and_directory_records(self):
        self.populate()
        self.check(False)

    def test_R4_head_counts_neighbours_and_skips_exact_and_directory_records(self):
        self.populate()
        self.commit("records and neighbours")
        self.check(True)

    def test_R4_a_same_named_directory_deeper_is_counted_without_a_lock(self):
        self.write("app/reviews/models.py", "def rec_app_reviews():\n    return 1\n")
        self.write("reviews/gen.py", "def rec_reviews():\n    return 1\n")
        self.commit("reviews")
        for at_head in (True, False):
            names = self.names(at_head)
            self.assertIn("rec_app_reviews", names, "at_head=%s" % at_head)
            self.assertNotIn("rec_reviews", names, "at_head=%s" % at_head)

    def test_R4_existing_non_record_skips_stay(self):
        skipped = {"tests/t.py": "skip_tests", "test/t.py": "skip_test", "pkg/tests/t.py": "skip_pkg_tests", ".venv/lib/v.py": "skip_venv",
                   "pkg/.venv/v.py": "skip_pkg_venv", "__pycache__/c.py": "skip_cache", "pkg/__pycache__/c.py": "skip_pkg_cache"}
        for rel, name in skipped.items():
            self.write(rel, "def %s():\n    return 1\n" % name)
        self.write("hunsu.py", "def rec_hunsu():\n    return 1\n")
        self.commit("skips")
        for at_head in (True, False):
            names = self.names(at_head)
            self.assertIn("rec_hunsu", names, "at_head=%s" % at_head)
            for name in skipped.values():
                self.assertNotIn(name, names, "at_head=%s: %s stays skipped" % (at_head, name))

    def test_R4_head_and_working_tree_agree_on_a_clean_committed_tree(self):
        self.populate()
        self.write(".other/dot.py", '"""dot."""\n\n\ndef rec_dot_dir():\n    # c\n    return 1\n')
        self.write("notes.rec", "r\n")
        self.commit("everything")
        head, work = worker.inventory(self.dir, at_head=True), worker.inventory(self.dir, at_head=False)
        self.assertEqual(head, work)
        self.assertIn("rec_hunsu", head[0])
        self.assertNotIn("rec_exact", head[0])


class R5Validators(RepoCase):
    def sibi(self, change):
        sibi = worker.load_member("sibi")
        before = worker.tree_state(self.dir)
        change()
        return worker.validate({"status": "done", "summary": "", "non-claims": [], "findings": []}, sibi, REQUEST, self.dir, "",
                               "claude-code", before)

    def test_R5_no_tree_changes_fails_a_call_that_changed_hunsu_named_sources(self):
        for rel in ("hunsu.py", "hunsu_helper.py", "hunsu-notes.md"):
            with self.subTest(rel=rel):
                out = self.sibi(lambda: self.write(rel, "x = 1\n"))
                self.assertEqual(out["status"], "failed", out)
                self.assertIn("no-tree-changes", out.get("validation", {}).get("failed", []), out)
                self.assertIn(rel, " ".join(out["non-claims"]), out)
                os.remove(os.path.join(self.dir, rel))

    def test_R5_no_tree_changes_fails_a_changed_committed_hunsu_py(self):
        self.write("hunsu.py", "x = 1\n")
        self.commit("hunsu.py")
        out = self.sibi(lambda: self.write("hunsu.py", "x = 2\n"))
        self.assertEqual(out["status"], "failed", out)
        self.assertIn("no-tree-changes", out.get("validation", {}).get("failed", []), out)

    def test_R5_no_tree_changes_passes_env_chongdae_and_declared_record_changes(self):
        self.lock({"record-paths": {"p": ["recs/"]}})
        self.commit("lock")
        changes = {"hunsu.lock.json": json.dumps({"record-paths": {"p": ["recs/"]}, "x": 1}), "hunsu-conflicts.md": "# c\n",
                   ".chongdae/run-1/state.json": "{}\n", "recs/a/b.json": "{}\n"}
        for rel, text in changes.items():
            with self.subTest(rel=rel):
                out = self.sibi(lambda: self.write(rel, text))
                self.assertEqual(out["status"], "done", out)

    def teujip(self, extra, transcript=""):
        teujip = worker.load_member("teujip")
        before = worker.tree_state(self.dir)
        self.write("tests/test_x.py", RED_TEST)
        extra()
        return worker.validate(fresh(TEUJIP_ANSWER), teujip, REQUEST, self.dir, transcript, "claude-code", before)

    def test_R5_only_tests_touched_fails_hunsu_helper_without_a_transcript(self):
        out = self.teujip(lambda: self.write("hunsu_helper.py", "x = 1\n"))
        self.assertEqual(out["status"], "failed", out)
        self.assertIn("only-tests-touched", out.get("validation", {}).get("failed", []), out)
        self.assertIn(QUOTE, out["non-claims"], out)

    def test_R5_only_tests_touched_fails_hunsu_helper_its_transcript_names(self):
        ts = claude_stream(("Write", {"file_path": self.dir + "/tests/test_x.py"}), ("Write", {"file_path": self.dir + "/hunsu_helper.py"}),
                           result=TEUJIP_ANSWER)
        out = self.teujip(lambda: self.write("hunsu_helper.py", "x = 1\n"), ts)
        self.assertEqual(out["status"], "failed", out)
        self.assertIn("only-tests-touched", out.get("validation", {}).get("failed", []), out)
        self.assertIn(QUOTE, out["non-claims"], out)

    def test_R5_only_tests_touched_passes_env_chongdae_and_declared_record_changes(self):
        self.lock({"record-paths": {"p": ["recs/"]}})
        self.commit("lock")
        changes = {"hunsu.lock.json": json.dumps({"record-paths": {"p": ["recs/"]}, "x": 1}), "hunsu-conflicts.md": "# c\n",
                   ".chongdae/run-1/state.json": "{}\n", "recs/a/b.json": "{}\n"}
        for rel, text in changes.items():
            with self.subTest(rel=rel):
                out = self.teujip(lambda: self.write(rel, text))
                self.assertEqual(out["status"], "done", out)
                self.assertNotIn("only-tests-touched", out.get("validation", {}).get("failed", []), out)
                os.remove(os.path.join(self.dir, "tests", "test_x.py"))


class R6TestsKept(RepoCase):
    def run_main(self, test, commit_change, change=True):
        self.write(test, "# original contract\n")
        self.commit("contract")
        outdir = tempfile.mkdtemp(prefix="hacheong-rec-out-")
        self.addCleanup(shutil.rmtree, outdir, True)
        req, resp = os.path.join(outdir, "request.json"), os.path.join(outdir, "response.json")
        with open(req, "w") as fh:
            json.dump(dict(REQUEST, target=self.dir, tests=[test], checks=[]), fh)

        def host(*args):
            if change:
                self.write(test, "# builder rewrote the contract\n")
            if commit_change:
                self.commit("changed test")
            return {"status": "done", "summary": "built", "verified": [], "decisions": [], "non-claims": []}, ""

        with mock.patch.object(worker, "claude", host), \
                mock.patch.object(sys, "argv", ["worker.py", "--member", "dakdol", "--request", req, "--response", resp]):
            self.assertEqual(worker.main(), 0)
        with open(resp) as fh:
            return json.load(fh)

    def test_R6_a_changed_test_at_a_record_path_is_refused(self):
        for test in (".chongdae/run-1/test_contract.py", "reviews/test_contract.py"):
            for committed in (False, True):
                with self.subTest(test=test, committed=committed):
                    out = self.run_main(test, committed)
                    self.assertEqual(out["status"], "failed", out)
                    self.assertIn("tests-kept", out.get("validation", {}).get("failed", []), out)

    def test_R6_a_changed_test_at_a_declared_record_directory_is_refused(self):
        self.lock({"record-paths": {"p": ["recs/"]}})
        out = self.run_main("recs/test_contract.py", True)
        self.assertEqual(out["status"], "failed", out)
        self.assertIn("tests-kept", out.get("validation", {}).get("failed", []), out)

    def test_R6_an_unchanged_test_at_a_record_path_is_kept(self):
        out = self.run_main("reviews/test_contract.py", False, change=False)
        self.assertEqual(out["status"], "done", out)


class R8DirectoryItself(RepoCase):
    """A directory record covers the directory's own path: a tracked symlink committed there and deleted is a record change."""

    def symlink(self, rel, to="README.md"):
        p = os.path.join(self.dir, rel)
        os.makedirs(os.path.dirname(p) or self.dir, exist_ok=True)
        try:
            os.symlink(to, p)
        except (OSError, NotImplementedError, AttributeError) as e:
            self.skipTest("this platform cannot make symlinks: %s" % e)

    def tracked_symlink_deleted(self, rel, lock=None, replace=False):
        if lock is not None:
            self.lock(lock)
        self.symlink(rel)
        self.commit("symlink at %s" % rel)
        os.remove(os.path.join(self.dir, rel))
        if replace:
            self.write(rel + "/a.json", "{}\n")
            self.write(rel + "/x/y.json", "{}\n")

    def assertNothingAt(self, rel, state):
        self.assertFalse([k for k in state if k == rel or k.startswith(rel + "/")],
                         "%s is a declared directory record: neither it nor anything under it may appear: %r" % (rel, state))

    def test_R8_is_record_covers_the_directory_path_itself_and_under_it(self):
        for path in ("reviews", "reviews/a.json", "reviews/x/y.json"):
            self.assertIs(worker.is_record(path, ["reviews/"]), True, path)
        for path in ("docs/rec", "docs/rec/x.json"):
            self.assertIs(worker.is_record(path, ["docs/rec/"]), True, path)
        self.assertIs(worker.is_record("reviews", ("hunsu.json", "reviews/", "notes.rec")), True)

    def test_R8_is_record_never_covers_a_prefix_sibling_of_a_directory(self):
        for path in ("reviews-old", "reviews-old/a.json", "reviews.py", "reviewsx", "reviews.", "review", ""):
            self.assertIs(worker.is_record(path, ["reviews/"]), False, path)
        for path in ("docs/record", "docs/rec.md", "x/docs/rec", "docs", "docs/re"):
            self.assertIs(worker.is_record(path, ["docs/rec/"]), False, path)

    def test_R8_is_record_directory_is_anchored_at_the_root(self):
        for path in ("src/reviews", "src/reviews/a.json", "/reviews", "./reviews"):
            self.assertIs(worker.is_record(path, ["reviews/"]), False, path)

    def test_R8_is_record_exact_file_covers_exactly_that_path(self):
        self.assertIs(worker.is_record("hunsu.json", ["hunsu.json"]), True)
        for path in ("hunsu.json/x", "hunsu.json.bak", "hunsu.jsonx", "hunsu", "sub/hunsu.json", "hunsu.json/"):
            self.assertIs(worker.is_record(path, ["hunsu.json"]), False, path)

    def test_R8_is_record_exact_file_is_never_made_a_directory_by_the_disk(self):
        self.write("mangsang/x.json", "{}\n")
        cwd = os.getcwd()
        os.chdir(self.dir)
        self.addCleanup(os.chdir, cwd)
        self.assertTrue(os.path.isdir("mangsang"))
        self.assertIs(worker.is_record("mangsang/x.json", ["mangsang"]), False)
        self.assertIs(worker.is_record("mangsang/x.json", ("mangsang",)), False)
        self.assertIs(worker.is_record("mangsang", ["mangsang"]), True)

    def test_R8_tree_state_bare_record_with_a_directory_on_disk_still_shows_its_children(self):
        self.lock({"record-paths": {"p": ["mangsang"]}})
        self.write("mangsang/x.json", "{}\n")
        self.assertVisible("mangsang/x.json", self.state())

    def test_R8_tree_state_deleted_symlink_at_a_declared_directory_is_left_out(self):
        self.tracked_symlink_deleted("reviews", lock=DECLARED)
        self.assertNothingAt("reviews", self.state())

    def test_R8_tree_state_deleted_symlink_at_the_fallback_directory_is_left_out_without_a_lock(self):
        self.assertFalse(os.path.exists(os.path.join(self.dir, "hunsu.lock.json")))
        self.tracked_symlink_deleted("reviews")
        self.assertNothingAt("reviews", self.state())

    def test_R8_tree_state_deleted_symlink_at_a_nested_declared_directory_is_left_out(self):
        self.tracked_symlink_deleted("docs/rec", lock=DECLARED)
        self.assertNothingAt("docs/rec", self.state())

    def test_R8_tree_state_deleted_symlink_replaced_by_a_real_directory_is_left_out(self):
        self.tracked_symlink_deleted("reviews", lock=DECLARED, replace=True)
        self.assertNothingAt("reviews", self.state())

    def test_R8_tree_state_deleted_symlink_replaced_by_a_real_directory_is_left_out_without_a_lock(self):
        self.tracked_symlink_deleted("reviews", replace=True)
        self.assertNothingAt("reviews", self.state())

    def test_R8_tree_state_deleted_symlink_at_an_undeclared_sibling_is_gone(self):
        for lock in (DECLARED, None):
            with self.subTest(lock=lock is not None):
                if lock is None and os.path.exists(os.path.join(self.dir, "hunsu.lock.json")):
                    os.remove(os.path.join(self.dir, "hunsu.lock.json"))
                    self.commit("no lock")
                self.tracked_symlink_deleted("reviews-old", lock=lock)
                s = self.state()
                self.assertEqual(s.get("reviews-old"), "gone", s)
                self.commit("deleted reviews-old")

    def sibi(self, change):
        sibi = worker.load_member("sibi")
        before = worker.tree_state(self.dir)
        change()
        return worker.validate({"status": "done", "summary": "", "non-claims": [], "findings": []}, sibi, REQUEST, self.dir, "",
                               "claude-code", before)

    def test_R8_no_tree_changes_passes_a_deleted_record_symlink(self):
        for lock in (DECLARED, None):
            with self.subTest(lock=lock is not None):
                if lock is not None:
                    self.lock(lock)
                self.symlink("reviews")
                self.commit("symlink")
                out = self.sibi(lambda: os.remove(os.path.join(self.dir, "reviews")))
                self.assertEqual(out["status"], "done", out)
                self.assertNotIn("no-tree-changes", out.get("validation", {}).get("failed", []), out)
                self.commit("deleted")
                if lock is not None:
                    os.remove(os.path.join(self.dir, "hunsu.lock.json"))
                    self.commit("no lock")

    def test_R8_no_tree_changes_passes_a_deleted_record_symlink_replaced_by_a_directory(self):
        self.lock(DECLARED)
        self.symlink("reviews")
        self.commit("symlink")

        def change():
            os.remove(os.path.join(self.dir, "reviews"))
            self.write("reviews/a.json", "{}\n")

        out = self.sibi(change)
        self.assertEqual(out["status"], "done", out)

    def test_R8_no_tree_changes_still_fails_a_deleted_symlink_at_an_undeclared_sibling(self):
        self.lock(DECLARED)
        self.symlink("reviews-old")
        self.commit("symlink")
        out = self.sibi(lambda: os.remove(os.path.join(self.dir, "reviews-old")))
        self.assertEqual(out["status"], "failed", out)
        self.assertIn("no-tree-changes", out.get("validation", {}).get("failed", []), out)


SIBLINGS = {"chongdae", "hunsu", "mangsang", "dwitbuk", "jokbo", "dakdol", "deomi", "tools"}


class R7NothingElse(unittest.TestCase):
    def test_R7_worker_imports_nothing_from_a_sibling_plugin(self):
        with open(os.path.join(HERE, "worker.py"), encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        local = {os.path.splitext(f)[0] for f in os.listdir(HERE) if f.endswith(".py")}
        stdlib = set(getattr(sys, "stdlib_module_names", ()))
        for node in ast.walk(tree):
            mods = []
            if isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                self.assertEqual(node.level, 0, "no relative import out of hacheong")
                mods = [node.module or ""]
            for m in mods:
                top = m.split(".")[0]
                self.assertNotIn(top, SIBLINGS, "worker.py imports %s" % m)
                if stdlib:
                    self.assertIn(top, stdlib | local, "worker.py imports %s, neither stdlib nor hacheong's own" % m)

    def test_R7_the_other_self_checks_keep_passing(self):
        for f in ("test_native_prompt.py", "test_hostcall_env.py"):
            with self.subTest(f=f):
                done = subprocess.run([sys.executable, "-m", "unittest", f], cwd=HERE, capture_output=True, text=True)
                self.assertEqual(done.returncode, 0, done.stderr[-2000:])


if __name__ == "__main__":
    unittest.main()
