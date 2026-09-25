# hacheong (하청)

The subcontractor of the LLM-development era: the people a plan hires by role. Each member is a **disposition**, not a
job — the same person can be sent at code today and at a plan or a design tomorrow — and each call is a fresh, bounded
process with one answer. One runner serves every member; a member is a directory (a role text, an answer schema, a
policy), so anyone can add one. What a member may not do is enforced after the fact by the runner, never merely asked
of the model.

| member | role key | when | reads | answers |
|---|---|---|---|---|
| **닥돌** dakdol | `build` | the build | the contract and the tree | the slice, `verified` checks, `decisions`, `non-claims` |
| **시비** sibi | `quibble` | before a build | the contract only | what is `undecided`, a `contradiction`, `unchecked` — each with a quote |
| **트집** teujip | `nitpick` | before a build | the contract only | the tests that will decide it, written to fail; the runner checks they are red |
| **초짜** chojja | `newbie` | after a build | what the person the work is for would get: the README and the program (a plan: the goal and the plan) | what `did-not-work`, is `unclear`, or a `surprise` — each with a quote |

## Install

```
claude plugin marketplace add guinjaaaaaaaaaaaaaaaaaaaaakeop/hacheong
claude plugin install hacheong@hacheong
```

Codex: `codex plugin marketplace add guinjaaaaaaaaaaaaaaaaaaaaakeop/hacheong`, `codex plugin add hacheong@hacheong`. A
project declares who it hires in hunsu.json: `"roles": {"implementer": "hacheong:build", "verifier": "dwitbuk:eyes"}`
— hunsu resolves `hacheong:build` to the argv below and locks it; chongdae spawns argv.

## How a member is called

```
python3 <plugin root>/worker.py --member <name> --request <chongdae/request@1> --response <file> [--host claude|codex] [--model M] [--effort E] [--max-turns N] [--domain D]
```

The runner assembles the prompt — `members/<name>/ROLE.md` ⊕ `domains/<domain>/DOMAIN.md` (its common part and the `##
<member>` section) ⊕ the request — starts a fresh host session with the member's `policy.json` (tools, sandbox, turn
budget) and `answer.json` as the enforced output schema, runs the member's validators over the answer and the
session's transcript, and writes the answer atomically with `worker` (host, model, turns, cost, session, the
transcript file kept next to it), `member` and `domain`. The domain comes from the request: `domain` if it says so,
else the artifact's family (`produces: plan/…` → `plan`), else `code`.

Every answer carries the envelope any runner reads — `status` (`done` | `blocked` | `failed`), `summary`, `non-claims`
— plus the member's own fields. A validator that fails makes the answer `failed` with the reason as a non-claim: an
answer that broke its own rules is not an answer.

`--prompt-only` prints the exact prompt instead of calling a host — for a session that dispatches its host's own
subagent (chongdae's `native:hacheong:quibble`) and writes the subagent's answer verbatim.

## Validators (the runner's, chosen per member in `policy.json`)

`quotes-required:<collection>.<field>` every item carries a non-empty quote · `no-tree-changes` the tree is as it was
(git) · `checks-ran` every `verified[].check` appears as a command in the transcript (compared as shell tokens:
quoting is not a difference) · `red-before-build` every file in `tests` fails now · `only-tests-touched` nothing
changed outside `tests` · `tests-kept` the request's `tests` are as they were when the session started (the working tree,
uncommitted changes included — put back to HEAD is changed too; a protected test that is not in the tree fails it, since nothing was kept) · `readme-only` no source file was opened (Read or
shell) — a newbie who peeked is tainted.

## Adding a member

`python3 <plugin root>/hacheong.py new <name>` scaffolds `members/<name>/` (ROLE.md with placeholders, answer.json,
policy.json); write the sentences, pick the kinds and validators, add one `roles` line to plugin.json (all three
copies), `hacheong.py check`, then `hacheong.py try <name> --request <a real request>` to see the validated answer. No
Python.

Three places a member can live, one runner: this plugin (`members/`); a project (`<project>/hacheong/members/<name>/`,
called as `--member ./hacheong/members/<name>` — the project's members and domains shadow the plugin's); another
plugin that ships its own `members/` and declares roles pointing at this runner (`{plugin:hacheong}/worker.py --member
{plugin:theirs}/members/x`). Domains the same way: `domains/<name>/DOMAIN.md` here or under the project's
`hacheong/domains/`.

## What is fixed

The request and the answer envelope (chongdae's request, `status/summary/non-claims`, `worker`), the host adapters,
the validator set. A member may not change these; when they must change, this plugin's version does.

## Limits

- Four domains shipped: `code`; `refactor` (placement changes, behavior and explanation do not: the runner compares
  the project's public names, docstrings and comment lines with HEAD and refuses a builder's answer where any shrank —
  `explanation-kept`; the nitpicker adds no placement tests; the eyes are told to look for words the diff removed and
  did not put back); `site` (a static site: the author follows the README and builds, the visitor reads the generated
  pages — 초짜 does both in a scratch copy, so the project is never touched); and `plan` (the artifact is the plan
  document itself: 닥돌 writes sections with acceptance sentences, 시비 quarrels with sentences that leave two readings or
  promise the unrequested, 트집 writes counter-examples, 초짜 reads it as the person who asked — for intent, not form; a
  plan still deciding has no slices yet, and a question answered by a survey is a `findings:` section carrying sources
  instead of acceptance sentences). A member sent at a domain
  with no text works from its role alone and says so.
- The prompt says where the session runs (`# Where you run`): a Codex `workspace-write` sandbox has no network by default
  and a read-only `.git`; a Claude Code session has the member's tools only. What the work needs and that place lacks is
  `blocked`, named — never a hand-written lock file or another tool in the named one's place.
- A member's session is a fresh process, but not an empty one: on Claude Code it receives the project's SessionStart
  modes (every enabled plugin's hook runs; `--setting-sources ""` does not keep them out, and the flag that would
  cannot stay logged in). A mode written for the person's session — "leave the code for the user to write" — reaches
  the builder too. hacheong does not filter modes; hunsu's judge reads each mode's injected text beside each member's
  prompt (`--prompt-only`), so the contradiction is found before a worker is hired, and the project's resolution
  decides.
- 닥돌 does not bend code to pass a contract test that contradicts the contract: it stops `blocked` with
  `disputed-tests` (the test, the contract sentence quoted, why), and a runner sends the dispute back to the test's
  writer. 트집 given a request with `amending` corrects the disputed tests to the contract (or keeps one and quotes
  why); `red-before-build` is waived there, since the build already stands.
- A validator sees the transcript, not the model's mind: `readme-only` catches reads it can see (tool calls,
  `cat`/`grep`/… in shell), not a model that already knew the code.
- chongdae hires these around a task: `add … --before quibble --after newbie` (or `before`/`after` on a plan task,
  `stages` on a plan). A `before` role's findings hold the task until a human accepts them; an `after` role's go to
  the record. `nitpick` is not a stage: 트집 is a task of its own (`add tests --role nitpick --tests …`), since its
  output is the contract's tests.

- `worker.py` starts its host session through `hostcall.py` — one host call for every worker of this family (hunsu's judge, mangsang's judge, dwitbuk's eyes,
  hacheong's members), vendored: the same file in each plugin, since a plugin imports no other plugin. The umbrella checkout's `tools/same-file.py` says when the copies drift.

- **What a tree check leaves out** (`no-tree-changes`, `only-tests-touched`, `tests-kept`, `explanation-kept`) — the products' records —
  comes from the lock's `record-paths` (each plugin's `records` declaration); without it, the names as they were.

## Versioning

Semver, and a version names one content: every change to the source — code, role text, this README — bumps the version
in all three manifests (`plugin.json`, `.claude-plugin/plugin.json`, `.codex-plugin/plugin.json`) and the marketplace
entries before it is used anywhere. **patch**: behavior or wording, every interface unchanged. **minor**: a new
member, field, validator or domain; what exists keeps working. **major**: the request, the envelope, or `worker`
changes shape.

## Self-check

`python3 test_hacheong.py` — members load and assemble, the host stream parses into an answer and nothing short of a
real one is `done`, each validator fires on a recorded case, project-local members and domains shadow the plugin's,
`new` scaffolds something `check` refuses until it is written. No model calls.
