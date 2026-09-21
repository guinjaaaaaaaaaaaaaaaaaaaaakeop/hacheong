---
name: hire
description: Use when a plan or the lock names a hacheong role (build, quibble, nitpick, newbie) as a task's provider, or when the person asks who can build, dispute, test or try a slice. Explains which member does what and how a runner or a session calls them; hacheong members are fresh processes with one answer each.
---

The engine is `worker.py` at this plugin's root. Members are directories under `members/`, domains under `domains/`.

- `build` (닥돌): the hands — builds one contracted slice, runs the checks, lists its decisions.
- `quibble` (시비): before a build — reads only the contract and reports what is undecided, contradictory or unchecked, each with a quote.
- `nitpick` (트집): before a build — writes the contract's tests to make the builder fail; the runner verifies they are red.
- `newbie` (초짜): after a build — README and the program only; tries it and reports what did not work, with quotes.

In a chongdae session run: `add <task> --role implementer --before quibble --after newbie` hires 닥돌 for the work with 시비 before and 초짜 after; `add tests --role nitpick --tests tests/test_x.py` has 트집 write the contract's tests as a task of its own. A runner (chongdae) calls a member with the argv this plugin declares as its role (plugin.json `roles`): `python3 <plugin root>/worker.py --member <name> --request <file> --response <file> --host claude|codex`. A session dispatching its own subagent instead (a `native:` provider) runs the same argv with `--prompt-only`, gives the printed prompt to a fresh subagent, and writes its JSON answer verbatim to the response path. Never do a member's work yourself and never edit its answer.

`python3 <plugin root>/hacheong.py roster` lists the members; `hacheong.py new <name>` scaffolds one; `hacheong.py check` validates them; `hacheong.py try <name> --request <file>` runs one against a request and shows the validated answer.
