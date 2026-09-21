"""hacheong — the subcontractor: the people a plan hires by role. This is the roster's front desk; worker.py does the work.

  roster [--target DIR]            the members here (and the project's own), with the role key each is declared under
  check  [--target DIR]            every member is well-formed: ROLE.md, answer.json parses, policy keys and validators known, roles ↔ members 1:1
  new    <name> [--target DIR]     scaffold a member — in this plugin, or in the project's hacheong/members/ with --target
  try    <name> --request FILE [--host claude|codex] [--model M] [--effort E]   run one member on a request; the validated answer, printed
  prompt <name> --request FILE     the exact prompt worker.py would send (worker.py --prompt-only)

A member is a directory: `ROLE.md` (who they are, in sentences), `answer.json` (the answer's schema; the envelope
status/summary/non-claims is always added), `policy.json` (`tools`, `sandbox`, `max-turns`, `validate`: which of the runner's
validators apply). Adding a member is adding a directory — and one line in plugin.json `roles` when it is this plugin's.
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import worker  # noqa: E402

TEMPLATE_ROLE = """# {name} — <one line: who this person is, in the project's own tone>

You are <the disposition: what stance you take, what you are for>. You read <exactly what — the contract? the README? the tree?>; you do not read <what would spoil the stance>.

You look for / you produce: <the one thing this member answers with>.

- <a rule the person keeps: e.g. every finding quotes what it is about>
- <what you never do: fix, suggest, rate, commit …>
- If there is nothing to report, say so: an empty answer with `status: done` is a good answer.
"""
TEMPLATE_ANSWER = {"type": "object", "additionalProperties": False,
                   "required": ["status", "summary", "findings", "non-claims"],
                   "properties": {"status": {"enum": ["done", "blocked", "failed"]}, "summary": {"type": "string"},
                                  "findings": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["kind", "where", "quote", "why"],
                                                                         "properties": {"kind": {"enum": ["<kind-1>", "<kind-2>"]}, "where": {"type": "string"},
                                                                                        "quote": {"type": "string"}, "why": {"type": "string"}}}},
                                  "non-claims": {"type": "array", "items": {"type": "string"}}}}
TEMPLATE_POLICY = {"tools": "Read,Grep,Glob", "sandbox": "read-only", "max-turns": 12, "validate": ["quotes-required:findings.quote", "no-tree-changes"]}


def declared_roles(root=HERE):
    """role key -> member name, from plugin.json `roles` (the argv's --member)."""
    out = {}
    for key, argv in (json.loads((root / "plugin.json").read_text(encoding="utf-8")).get("roles") or {}).items():
        if isinstance(argv, list) and "--member" in argv:
            out[key] = argv[argv.index("--member") + 1]
    return out


def members_in(base):
    return sorted(p.name for p in base.iterdir() if p.is_dir() and not p.name.startswith(".")) if base.is_dir() else []


def cmd_roster(args):
    roles = declared_roles()
    by_member = {m: k for k, m in roles.items()}
    print("hacheong members (this plugin):")
    for m in members_in(HERE / "members"):
        first = (HERE / "members" / m / "ROLE.md").read_text(encoding="utf-8").split("\n", 1)[0].lstrip("# ").strip() if (HERE / "members" / m / "ROLE.md").exists() else "(no ROLE.md)"
        print("  %-10s role: %-9s %s" % (m, by_member.get(m, "-"), first))
    if args.target:
        local = Path(args.target) / "hacheong" / "members"
        if members_in(local):
            print("project members (%s):" % local)
            for m in members_in(local):
                print("  %-10s (argv: python3 {plugin:hacheong}/worker.py --member %s …)" % (m, "./hacheong/members/" + m))
    return 0


def problems_of(base, roles=None):
    """Everything wrong with the members under `base`; empty when they are all well-formed."""
    out = []
    names = members_in(base)
    for m in names:
        d = base / m
        for f in ("ROLE.md", "answer.json", "policy.json"):
            if not (d / f).exists():
                out.append("%s: missing %s" % (m, f))
        try:
            mem = worker.load_member(str(d))
        except SystemExit as err:
            out.append("%s: %s" % (m, err))
            continue
        if "<" in mem["role"] and ">" in mem["role"]:
            out.append("%s: ROLE.md still has template placeholders (<…>)" % m)
        enum = mem["schema"].get("properties", {}).get("findings", {}).get("items", {}).get("properties", {}).get("kind", {}).get("enum", [])
        if any(str(e).startswith("<") for e in enum):
            out.append("%s: answer.json still has template kinds (<…>)" % m)
        for v in mem["policy"].get("validate", []):
            name, _, arg = v.partition(":")
            if name in ("quotes-required",) and not arg:
                out.append("%s: validator %s needs an argument (collection.field)" % (m, name))
            if name == "quotes-required" and arg.split(".")[0] not in mem["schema"].get("properties", {}):
                out.append("%s: validator %s names %r, not in answer.json" % (m, v, arg.split(".")[0]))
            if name in ("red-before-build", "only-tests-touched") and "tests" not in mem["schema"].get("properties", {}):
                out.append("%s: validator %s needs a `tests` field in answer.json" % (m, name))
            if name == "checks-ran" and "verified" not in mem["schema"].get("properties", {}):
                out.append("%s: validator checks-ran needs a `verified` field in answer.json" % m)
    if roles is not None:
        for key, m in roles.items():
            if m not in names:
                out.append("roles[%s] names member %r, which has no directory" % (key, m))
        for m in names:
            if m not in roles.values():
                out.append("member %s is not declared under any role in plugin.json" % m)
    return out


def cmd_check(args):
    probs = problems_of(HERE / "members", declared_roles())
    if args.target and (Path(args.target) / "hacheong" / "members").is_dir():
        probs += ["project " + p for p in problems_of(Path(args.target) / "hacheong" / "members")]
    for p in probs:
        print("  error %s" % p)
    print("hacheong check: %d member(s), %d error(s)" % (len(members_in(HERE / "members")), len(probs)))
    return 1 if probs else 0


def cmd_new(args):
    base = (Path(args.target) / "hacheong" / "members") if args.target else (HERE / "members")
    d = base / args.name
    if d.exists():
        raise SystemExit("%s exists" % d)
    d.mkdir(parents=True)
    (d / "ROLE.md").write_text(TEMPLATE_ROLE.format(name=args.name), encoding="utf-8")
    (d / "answer.json").write_text(json.dumps(TEMPLATE_ANSWER, indent=2) + "\n", encoding="utf-8")
    (d / "policy.json").write_text(json.dumps(TEMPLATE_POLICY, indent=2) + "\n", encoding="utf-8")
    where = "the project's hacheong/members" if args.target else "this plugin's members"
    print("scaffolded %s in %s: edit ROLE.md (the <…> placeholders), answer.json (the kinds), policy.json (tools, validators)%s"
          % (args.name, where, "" if args.target else "; then add a `roles` line in plugin.json (all three copies) and run `hacheong.py check`"))
    return 0


def cmd_try(args):
    resp = args.response or os.path.join(tempfile.mkdtemp(prefix="hacheong-try-"), args.name.replace("/", "_") + ".response.json")
    cmd = [sys.executable, str(HERE / "worker.py"), "--member", args.name, "--request", args.request, "--response", resp, "--host", args.host]
    for flag, val in (("--model", args.model), ("--effort", args.effort), ("--domain", args.domain)):
        if val:
            cmd += [flag, val]
    done = subprocess.run(cmd, text=True, capture_output=True, encoding="utf-8", errors="replace")
    sys.stdout.write(done.stdout)
    if done.returncode:
        sys.stdout.write(done.stderr)
        return done.returncode
    out = json.loads(Path(resp).read_text(encoding="utf-8"))
    print(json.dumps(out, ensure_ascii=False, indent=2))
    w = out.get("worker") or {}
    print("-- %s · %s · %s turns · $%s · validators %s" % (out.get("status"), w.get("model"), w.get("turns", "?"), w.get("cost_usd", "?"),
                                                           "failed: " + ", ".join(out["validation"]["failed"]) if out.get("validation") else "passed"))
    return 0


def cmd_prompt(args):
    return subprocess.call([sys.executable, str(HERE / "worker.py"), "--member", args.name, "--request", args.request, "--response", "/dev/null", "--prompt-only"] + (["--domain", args.domain] if args.domain else []))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("roster"); p.add_argument("--target", default=None)
    p = sub.add_parser("check"); p.add_argument("--target", default=None)
    p = sub.add_parser("new"); p.add_argument("name"); p.add_argument("--target", default=None, help="scaffold in this project's hacheong/members/ instead of the plugin's")
    for name in ("try", "prompt"):
        p = sub.add_parser(name); p.add_argument("name"); p.add_argument("--request", required=True); p.add_argument("--domain", default=None)
        if name == "try":
            p.add_argument("--host", choices=["claude", "codex"], default="claude"); p.add_argument("--model", default=None); p.add_argument("--effort", default=None)
            p.add_argument("--response", default=None, help="where to write the answer (default: a temp dir)")
    args = ap.parse_args(argv)
    return {"roster": cmd_roster, "check": cmd_check, "new": cmd_new, "try": cmd_try, "prompt": cmd_prompt}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
