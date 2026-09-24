"""hacheong's one runner: a member (a disposition), a domain (what the artifact is), a request — one fresh host session, one answer.

  python worker.py --member NAME|DIR --request FILE --response FILE [--host claude|codex] [--model M] [--effort E] [--max-turns N]
  python worker.py --member NAME --request FILE --response FILE --prompt-only      # print the prompt; a session dispatches its own subagent

A member is a directory, not code: `ROLE.md` (the disposition, as sentences), `answer.json` (the answer's schema), `policy.json`
(tools, sandbox, which of this runner's validators apply). A domain is `domains/<name>/DOMAIN.md`: what "build", "quibble",
"nitpick", "newbie" mean for that kind of artifact and what counts as evidence there. The prompt is ROLE ⊕ DOMAIN ⊕ request.
A name resolves to `members/<name>` here, a project's `hacheong/members/<name>` first; a path with a slash is used as is.

The answer always carries the envelope every runner reads — `status` (done|blocked|failed), `summary`, `non-claims` — plus
the member's own fields, plus `worker` (host, model, turns, cost, session, transcript). What a model cannot be asked to
refrain from is enforced here after the fact by named validators (a quote for every finding, a tree it was not allowed to
change, a check it claims to have run, a test that must be red before the build, a README-only reader): a validator that
fails turns the answer into `status: failed` with the reason in `non-claims`. Nothing short of a validated answer is done.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENVELOPE = {"status": {"enum": ["done", "blocked", "failed"]}, "summary": {"type": "string"}, "non-claims": {"type": "array", "items": {"type": "string"}}}
POLICY_KEYS = {"tools", "sandbox", "validate", "max-turns"}
VALIDATORS = ("quotes-required", "no-tree-changes", "checks-ran", "red-before-build", "readme-only", "only-tests-touched", "explanation-kept")


def py_inventory(text):
    """What a Python file says besides what it does: its public def/class names, how many docstrings, how many comment
    lines. A refactoring may move all of these; it may not lose any. Text that will not parse counts as nothing (a broken
    file fails its checks anyway)."""
    import ast, io as _io, tokenize
    names, docs = set(), 0
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return names, docs, 0
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if not node.name.startswith("_"):
                names.add(node.name)
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and ast.get_docstring(node):
            docs += 1
    comments = 0
    try:
        for t in tokenize.generate_tokens(_io.StringIO(text).readline):
            if t.type == tokenize.COMMENT:
                comments += 1
    except (tokenize.TokenError, IndentationError):
        pass
    return names, docs, comments


def inventory(target, at_head):
    """The project's Python inventory as one triple (names, docstrings, comment lines), summed over its .py files — at HEAD
    (from git) or in the working tree. Tests and records are left out: tests are the contract's, records are not the program."""
    skip = (".git/", ".chongdae/", ".mangsang/", ".dwitbuk/", "__pycache__/", ".venv/", "tests/", "test/")
    files = {}
    if at_head:
        done = subprocess.run(["git", "ls-tree", "-r", "--name-only", "HEAD"], cwd=target, capture_output=True, text=True, encoding="utf-8", errors="replace")
        for p in done.stdout.split("\n"):
            p = p.strip()
            if p.endswith(".py") and not p.startswith(skip) and not any("/" + s in "/" + p for s in skip):
                shown = subprocess.run(["git", "show", "HEAD:" + p], cwd=target, capture_output=True, text=True, encoding="utf-8", errors="replace")
                if shown.returncode == 0:
                    files[p] = shown.stdout
    else:
        for root, dirs, names in os.walk(target):
            rel = os.path.relpath(root, target).replace(os.sep, "/") + "/"
            dirs[:] = [d for d in dirs if not (rel.lstrip("./") + d + "/").startswith(skip) and d + "/" not in skip]
            for n in names:
                if n.endswith(".py"):
                    try:
                        files[(rel.lstrip("./") + n).lstrip("/")] = open(os.path.join(root, n), encoding="utf-8", errors="replace").read()
                    except OSError:
                        pass
    names, docs, comments = set(), 0, 0
    for text in files.values():
        n, d, c = py_inventory(text)
        names |= n; docs += d; comments += c
    return names, docs, comments


# ---------------------------------------------------------------- members and domains (directories, not code)

def member_dir(name, target=None):
    """`members/<name>` — a project's own `hacheong/members/<name>` wins; a path with a slash is taken as is."""
    if "/" in name or os.sep in name:
        p = Path(name)
        p = p if p.is_absolute() else Path(target or ".") / p
        if not p.is_dir():
            raise SystemExit("no member directory %s" % name)
        return p
    for base in ([Path(target) / "hacheong" / "members"] if target else []) + [HERE / "members"]:
        if (base / name).is_dir():
            return base / name
    raise SystemExit("no member %r — members here: %s" % (name, ", ".join(sorted(p.name for p in (HERE / "members").iterdir() if p.is_dir())) or "none"))


def load_member(name, target=None):
    d = member_dir(name, target)
    role = (d / "ROLE.md").read_text(encoding="utf-8") if (d / "ROLE.md").exists() else None
    if not role or not role.strip():
        raise SystemExit("member %s has no ROLE.md" % d.name)
    try:
        schema = json.loads((d / "answer.json").read_text(encoding="utf-8"))
        policy = json.loads((d / "policy.json").read_text(encoding="utf-8")) if (d / "policy.json").exists() else {}
    except (OSError, ValueError) as err:
        raise SystemExit("member %s: %s" % (d.name, err))
    unknown = set(policy) - POLICY_KEYS
    if unknown:
        raise SystemExit("member %s: policy.json has unknown keys %s (known: %s)" % (d.name, sorted(unknown), sorted(POLICY_KEYS)))
    bad = [v for v in policy.get("validate", []) if v.split(":")[0] not in VALIDATORS]
    if bad:
        raise SystemExit("member %s: unknown validators %s (this runner has: %s)" % (d.name, bad, ", ".join(VALIDATORS)))
    # the envelope is not the member's to drop: every runner reads status/summary/non-claims
    props = schema.setdefault("properties", {})
    for k, v in ENVELOPE.items():
        props.setdefault(k, v)
    req = schema.setdefault("required", [])
    for k in ENVELOPE:
        if k not in req:
            req.append(k)
    schema.setdefault("type", "object")
    schema.setdefault("additionalProperties", False)
    return {"name": d.name, "dir": d, "role": role.strip(), "schema": schema, "policy": policy}


def domain_for(request, override=None):
    """Which domain the request is about. Said outright (`domain`), else read off the artifact: checks or a build/verify
    stage → code; a `produces` type names its family (plan/…, design/…); else code."""
    if override:
        return override
    if request.get("domain"):
        return request["domain"]
    produces = str(request.get("produces") or "")
    if produces and "/" in produces:
        fam = produces.split("/")[0]
        if fam not in ("chongdae",):
            return fam
    return "code"


def domain_text(domain, member, target=None):
    """DOMAIN.md's common part (before the first `## `) plus the `## <member>` section, if any. A project's
    `hacheong/domains/<domain>/DOMAIN.md` wins over this plugin's. No file: the member works from its ROLE alone and says so."""
    for base in ([Path(target) / "hacheong" / "domains"] if target else []) + [HERE / "domains"]:
        p = base / domain / "DOMAIN.md"
        if p.exists():
            text = p.read_text(encoding="utf-8")
            parts = re.split(r"^## +", text, flags=re.M)
            common = parts[0].strip()
            mine = next((s for s in parts[1:] if s.split("\n", 1)[0].strip() == member), None)
            return (common + ("\n\n## " + mine.strip() if mine else "")).strip(), str(p)
    return None, None


def assemble(member, request, domain, target=None):
    dtext, dpath = domain_text(domain, member["name"], target)
    parts = ["# Who you are\n\n" + member["role"]]
    if dtext:
        parts.append("# The domain: %s\n\n%s" % (domain, dtext))
    else:
        parts.append("# The domain: %s\n\nNo domain text is available for %r. Work from your role alone and say so in `non-claims`." % (domain, domain))
    parts.append("# Request\n\nWork only inside `target`. Do not write the response file; answer with the JSON object.\n\n" + json.dumps(request, ensure_ascii=False, indent=2))
    return "\n\n".join(parts), dpath


# ---------------------------------------------------------------- host adapters (the same on every member)

def failed(summary, why, schema=None):
    return {"status": "failed", "summary": summary, "non-claims": [why]}


def parse_claude(returncode, stdout, stderr):
    """The host's stream-json -> the answer. Anything short of a well-formed answer is `failed`, never `done`."""
    result = None
    for line in stdout.split("\n"):
        if line.strip():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if isinstance(event, dict) and event.get("type") == "result":
                result = event
    if returncode or not result or result.get("is_error"):
        return failed("host exited %d: %s" % (returncode, (result or {}).get("subtype") or stderr[-400:]),
                      "the host session did not finish; nothing it did is verified")
    out = result.get("structured_output")
    if out is None:
        try:
            out = json.loads(result.get("result", "").strip())
        except ValueError:
            return failed("no structured answer", "answer was not the required JSON")
    if not isinstance(out, dict) or out.get("status") not in ("done", "blocked", "failed"):
        return failed("answer has no valid status", "answer did not match the schema")
    for key, default in (("non-claims", []), ("summary", "")):
        out.setdefault(key, default)
    return out


def claude(prompt, member, args, target):
    tools = member["policy"].get("tools", "Read,Grep,Glob")
    cmd = ["claude", "-p", "--output-format", "stream-json", "--verbose", "--no-session-persistence", "--setting-sources", "",
           "--strict-mcp-config", "--tools", tools, "--allowedTools", tools, "--max-turns", str(args.max_turns),
           "--json-schema", json.dumps(member["schema"]), "--add-dir", target, "--permission-mode", "bypassPermissions"]
    if args.model:
        cmd += ["--model", args.model]
    if args.effort:
        cmd += ["--effort", args.effort]
    done = subprocess.run(cmd, input=prompt.encode("utf-8"), capture_output=True, cwd=target,
                          env=dict(os.environ, CLAUDE_CODE_DISABLE_AUTO_MEMORY="1", AGENT_WORKER="1"))
    stdout = done.stdout.decode("utf-8", "replace")
    out = parse_claude(done.returncode, stdout, done.stderr.decode("utf-8", "replace"))
    out["worker"] = worker_record(stdout, args.response, "claude-code", args.model)
    return out, stdout


def codex(prompt, member, args, target):
    tmp = tempfile.mkdtemp(prefix="hacheong-")
    schema_path, out_path = os.path.join(tmp, "schema.json"), os.path.join(tmp, "last.txt")
    Path(schema_path).write_text(json.dumps(member["schema"]), encoding="utf-8")
    sandbox = os.environ.get("AGENT_CODEX_SANDBOX") or member["policy"].get("sandbox") or "read-only"
    cmd = [shutil.which("codex") or "codex", "exec", "--json", "--skip-git-repo-check", "--output-schema", schema_path, "-o", out_path, "-C", target, "-s", sandbox]
    if args.model:
        cmd += ["-m", args.model]
    if args.effort:
        cmd += ["-c", "model_reasoning_effort=%s" % json.dumps(args.effort)]
    cmd.append("-")
    done = subprocess.run(cmd, input=prompt.encode("utf-8"), capture_output=True, env=dict(os.environ, AGENT_WORKER="1"))
    try:
        out = json.loads(Path(out_path).read_text(encoding="utf-8").strip())
        if not isinstance(out, dict) or out.get("status") not in ("done", "blocked", "failed"):
            out = failed("answer has no valid status", "answer did not match the schema")
    except (OSError, ValueError):
        out = failed("codex exited %d without a JSON answer" % done.returncode, "the host session did not finish; nothing it did is verified")
    stdout = done.stdout.decode("utf-8", "replace")
    out["worker"] = worker_record(stdout, args.response, "codex", args.model, done.stderr.decode("utf-8", "replace"))
    return out, stdout


def worker_record(stdout_text, response_path, host, model=None, stderr_text=None):
    """Who did this call, from the host's own account — model, turns, cost, session — with the whole stream kept next to the
    response as `<response>.transcript.jsonl`. The runner copies this into `performed_by`; an answer whose procedure is not on
    disk cannot be audited. Claude Code says it in its stream (`init`, `result`); Codex's `--json` stream has the thread id and
    the model is in the rollout it keeps for that thread (`turn_context.model`)."""
    rec = {"host": host, "model": model}
    if host == "codex":
        m = re.search(r'"thread_id":\s*"([^"]+)"', stdout_text or "")
        if m:
            rec["session"] = m.group(1)
            home = os.environ.get("HUNSU_CODEX_DIR") or os.environ.get("CODEX_HOME") or os.path.join(os.path.expanduser("~"), ".codex")
            for dirpath, _, files in os.walk(os.path.join(home, "sessions")):
                for f in files:
                    if f.endswith(m.group(1) + ".jsonl"):
                        with open(os.path.join(dirpath, f), encoding="utf-8", errors="replace") as fh:
                            for line in fh:
                                mm = re.search(r'"turn_context".*?"model":\s*"([^"]+)"', line)
                                if mm:
                                    rec["model"] = rec["model"] or mm.group(1)
                                    ee = re.search(r'"effort":\s*"([^"]+)"', line)
                                    if ee:
                                        rec["effort"] = ee.group(1)
                                    break
        for key, name in (("model", "model"), ("session id", "session"), ("reasoning effort", "effort")):
            mh = re.search(r"^%s:\s*(.+?)\s*$" % re.escape(key), stderr_text or "", re.M)
            if mh and not rec.get(name):
                rec[name] = mh.group(1)
        kept = "".join(x for x in (stderr_text, stdout_text) if x)
        if kept:
            path = re.sub(r"\.json$", "", response_path) + ".transcript.jsonl"
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(kept if kept.endswith("\n") else kept + "\n")
            rec["transcript"] = os.path.basename(path)
        return rec
    if stdout_text is None:
        return rec
    for line in stdout_text.split("\n"):
        try:
            event = json.loads(line) if line.strip() else None
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get("type") == "system" and event.get("subtype") == "init":
            rec["model"] = event.get("model") or model
        elif event.get("type") == "result":
            rec["turns"], rec["cost_usd"], rec["session"] = event.get("num_turns"), event.get("total_cost_usd"), event.get("session_id")
    path = re.sub(r"\.json$", "", response_path) + ".transcript.jsonl"
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(stdout_text if stdout_text.endswith("\n") else stdout_text + "\n")
    rec["transcript"] = os.path.basename(path)
    return rec


# ---------------------------------------------------------------- validators: what the model cannot be asked to refrain from

def tree_state(target):
    """Every tracked-or-untracked file's hash, from git; None when the target is not a repository."""
    done = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"], cwd=target, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if done.returncode:
        return None
    state = {}
    for line in done.stdout.splitlines():
        path = line[3:].split(" -> ")[-1].strip().strip('"')
        if "__pycache__" in path or path.endswith((".pyc", ".DS_Store")):   # what interpreters and the OS leave behind is not a change
            continue
        if path.startswith((".chongdae/", ".dwitbuk/", ".mangsang/")):   # the run's record — where this worker's own transcript lands — is not the project
            continue
        full = os.path.join(target, path)
        state[path] = hashlib.sha1(open(full, "rb").read()).hexdigest() if os.path.isfile(full) else "gone"
    return state


def transcript_commands(stream_text, host):
    """The shell commands and file reads a session made, from its stream — what it actually did, not what it says."""
    cmds, reads = [], []
    for line in (stream_text or "").split("\n"):
        try:
            d = json.loads(line) if line.strip() else None
        except ValueError:
            continue
        if not isinstance(d, dict):
            continue
        if host == "codex":
            it = d.get("item") or {}
            if d.get("type") == "item.completed" and it.get("type") == "command_execution":
                cmds.append(it.get("command", ""))
        elif d.get("type") == "assistant":
            for c in (d.get("message") or {}).get("content", []):
                if c.get("type") == "tool_use":
                    inp = c.get("input") or {}
                    if c.get("name") == "Bash":
                        cmds.append(inp.get("command", ""))
                    elif c.get("name") in ("Read", "Edit", "Write", "Glob", "Grep"):
                        reads.append(inp.get("file_path") or inp.get("path") or inp.get("pattern") or "")
    return cmds, reads


def shell_tokens(command):
    """A command as its argv: the host's `/bin/zsh -lc "..."` wrapper unwrapped, quoting resolved. Unparseable text stays whole."""
    import shlex
    c = str(command).strip()
    m = re.match(r"^(?:/bin/)?(?:ba|z)?sh -l?c (.*)$", c, re.S)
    try:
        if m:
            c = shlex.split(m.group(1))[0]
        return shlex.split(c)
    except ValueError:
        return c.split()


def contains(seq, sub):
    """`sub` occurs in `seq` as a contiguous run (a check run as part of a longer command line still ran)."""
    n = len(sub)
    return n > 0 and any(seq[i:i + n] == sub for i in range(len(seq) - n + 1))


def validate(out, member, request, target, stream_text, host, before):
    """Run the member's declared validators. Each failure is written into the answer as a non-claim and the status becomes
    `failed` — an answer that broke its own rules is not an answer, whatever it says about itself."""
    problems = []
    cmds, reads = transcript_commands(stream_text, host)
    for spec in member["policy"].get("validate", []):
        name, _, arg = spec.partition(":")
        if name == "quotes-required":
            # arg: "findings.quote" — every item of `findings` has a non-empty `quote`
            coll, _, field = arg.partition(".")
            items = out.get(coll) or []
            missing = [i for i, f in enumerate(items) if not isinstance(f, dict) or not str(f.get(field or "quote", "")).strip()]
            if missing:
                problems.append("quotes-required: %s[%s] carry no %s — a finding without a quote is an opinion" % (coll, ",".join(map(str, missing)), field or "quote"))
        elif name == "no-tree-changes":
            after = tree_state(target)
            if before is not None and after is not None and after != before:
                changed = sorted(set(k for k in set(before) | set(after) if before.get(k) != after.get(k)))
                problems.append("no-tree-changes: the tree changed (%s) — this member may not touch the project" % ", ".join(changed[:8]))
        elif name == "checks-ran":
            # every `verified[].check` must appear as (part of) a command the session actually ran — compared as shell tokens,
            # not as text: `-p 'test_s[12].py'` ran quoted (the shell would glob it) and is the same argv reported unquoted
            ran = [shell_tokens(c) for c in cmds]
            for v in out.get("verified") or []:
                check = re.sub(r"\s*\(.*\)\s*$", "", str((v or {}).get("check", ""))).strip()   # a trailing remark — "(8 tests, OK)" — is not part of the command
                toks = shell_tokens(check)
                core = toks[1:] if len(toks) > 1 else toks   # drop the interpreter: python vs python3
                if check and not any(contains(r, toks) or (core and contains(r, core)) for r in ran):
                    problems.append("checks-ran: `%s` is claimed verified but no such command appears in the session's transcript (report the argv you ran, nothing else)" % check)
        elif name == "red-before-build":
            # the tests this member wrote must fail now: a contract test that passes before the build decides nothing. Not when
            # the request amends tests the build disputed (`amending`): the build already stands, and the corrected tests may pass
            if request.get("amending"):
                continue
            for t in out.get("tests") or []:
                p = os.path.join(target, t)
                if not os.path.exists(p):
                    problems.append("red-before-build: %s does not exist" % t)
                    continue
                py = "python3" if shutil.which("python3") else "python"
                done = subprocess.run([py, "-m", "unittest", t], cwd=target, capture_output=True, text=True, encoding="utf-8", errors="replace")
                if done.returncode == 0:
                    problems.append("red-before-build: %s passes before the build — it decides nothing" % t)
        elif name == "only-tests-touched":
            after = tree_state(target)
            if before is not None and after is not None:
                changed = sorted(set(k for k in set(before) | set(after) if before.get(k) != after.get(k)))
                allowed = set(out.get("tests") or [])
                stray = [c for c in changed if c not in allowed and not c.startswith(("tests/", "test/"))]
                if stray:
                    problems.append("only-tests-touched: changed outside the tests it declared: %s" % ", ".join(stray[:8]))
        elif name == "explanation-kept":
            # a refactoring keeps what the program says about itself: no public name, docstring or comment present at HEAD is
            # gone from the tree. Counted over the whole project, since moving is the point. Only in the refactor domain;
            # elsewhere a build may rightly delete. (A site's split lost 11 docstrings and 15 comments; a second task restored them.)
            if request.get("domain") != "refactor":
                continue
            names0, docs0, comm0 = inventory(target, at_head=True)
            names1, docs1, comm1 = inventory(target, at_head=False)
            lost = sorted(names0 - names1)
            gone = []
            if lost:
                gone.append("public names gone: %s" % ", ".join(lost[:8]))
            if docs1 < docs0:
                gone.append("docstrings %d -> %d" % (docs0, docs1))
            if comm1 < comm0:
                gone.append("comment lines %d -> %d" % (comm0, comm1))
            if gone:
                problems.append("explanation-kept: a refactoring moves code and keeps what it says about itself; against HEAD, %s — put them back where the code went" % "; ".join(gone))
        elif name == "readme-only":
            # a newbie reads docs and runs the program; opening source is peeking. Bash reads count too.
            doc = re.compile(r"(^|/)(README[^/]*|readme[^/]*|docs?/|CHANGELOG[^/]*|LICENSE[^/]*)$|\.md$", re.I)
            if request.get("domain") == "site":
                # a site's product is its generated pages: reading one is what a visitor does, not peeking at the source
                doc = re.compile(doc.pattern + r"|\.(?:html?|css|png|jpe?g|gif|svg|webp|xml|txt)$", re.I)
            readers = re.compile(r"^\s*(?:\w+=\S+\s+)*(cat|less|more|head|tail|sed|awk|grep|rg|bat|vim|nano|view|strings|od|xxd)\b")

            def in_project(tok):   # a file of the project tree (not the scratch dir, not the program being *run*)
                full = tok if os.path.isabs(tok) else os.path.join(target, tok)
                try:
                    return os.path.isfile(full) and os.path.realpath(full).startswith(os.path.realpath(target) + os.sep)
                except OSError:
                    return False
            peeked = [r for r in reads if r and not doc.search(r) and in_project(r)]
            for c in cmds:
                for seg in re.split(r"\|\||&&|[;|\n]", c):   # each pipeline segment on its own: `cat todo.json | python3 todo.py` reads the json, runs the py
                    if readers.search(seg):
                        for tok in re.findall(r"[\w./-]+", seg):
                            if "." in tok and not doc.search(tok) and in_project(tok):
                                peeked.append(tok)
            if peeked:
                problems.append("readme-only: read what a newbie would not (%s) — the report is tainted by knowledge of the source" % ", ".join(sorted(set(peeked))[:8]))
    if problems:
        out["status"] = "failed"
        out.setdefault("non-claims", []).extend(problems)
        out["validation"] = {"failed": [p.split(":")[0] for p in problems]}
    return out


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--member", required=True, help="a member's name (members/<name>, or the project's hacheong/members/<name>) or a directory")
    ap.add_argument("--request", required=True)
    ap.add_argument("--response", required=True)
    ap.add_argument("--host", choices=["claude", "codex"], default="claude")
    ap.add_argument("--model", default=None)
    ap.add_argument("--effort", default=None)
    ap.add_argument("--max-turns", type=int, default=None, help="turn budget (default: the member's policy `max-turns`, else 40)")
    ap.add_argument("--domain", default=None, help="override the domain the request implies (code, plan, design, …)")
    ap.add_argument("--prompt-only", action="store_true", help="print the prompt this call would send and exit — for a session that dispatches the host's own subagent (a `native:` provider)")
    args = ap.parse_args()
    request = json.loads(Path(args.request).read_text(encoding="utf-8"))
    if request.get("artifact-type") != "chongdae/request@1":
        raise SystemExit("not a chongdae request: %s" % args.request)
    target = request.get("target") or os.getcwd()
    member = load_member(args.member, target)
    if args.max_turns is None:
        args.max_turns = int(member["policy"].get("max-turns", os.environ.get("HACHEONG_MAX_TURNS", 40)))
    domain = domain_for(request, args.domain)
    prompt, _ = assemble(member, request, domain, target)
    if args.prompt_only:
        print(prompt + "\n\n# Answer\n\nYour whole final message is one JSON object, nothing else, matching this schema:\n" + json.dumps(member["schema"]))
        return 0
    before = tree_state(target)
    out, stream = (claude if args.host == "claude" else codex)(prompt, member, args, target)
    out = validate(out, member, request, target, stream, "codex" if args.host == "codex" else "claude-code", before)
    out["member"] = member["name"]
    out["domain"] = domain
    Path(args.response).parent.mkdir(parents=True, exist_ok=True)
    with open(args.response + ".tmp", "w", encoding="utf-8", newline="\n") as fh:   # LF on every host; the response is diffed and fingerprinted
        fh.write(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
    os.replace(args.response + ".tmp", args.response)   # whole or absent: the runner polls for this file
    print("%s (%s, %s) -> %s" % (out.get("status"), member["name"], domain, args.response))
    return 0


if __name__ == "__main__":
    sys.exit(main())
