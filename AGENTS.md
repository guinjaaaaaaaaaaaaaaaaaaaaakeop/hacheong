# Maintaining hacheong

This file governs work in this source repository. The installed hiring procedure has one source:
[plugin/skills/hire/SKILL.md](plugin/skills/hire/SKILL.md). Use that skill when hiring members; maintaining the plugin does not
itself call a member. See [plugin/README.md](plugin/README.md#shared-guidance-and-hosts) for host integration and CLI entry points.

- The payload is `plugin/`; runtime lives only there. Keep member roles, answer schemas and policies in
  `plugin/members/`, domain guidance in `plugin/domains/`, and enforcement in `plugin/worker.py`.
  Preserve the request and answer envelopes when changing a validator. Nothing for development goes under `plugin/`.
- Keep `plugin/hostcall.py` self-contained; an installed plugin must not import another plugin's checkout.
- Keep the shared procedure in `plugin/skills/`. Host manifests and adapters carry host-specific settings, not a second
  copy of the workflow. Keep `CLAUDE.md` as the single `@AGENTS.md` import.
- The suites stay at the root and import from `plugin/` explicitly. For behavioral changes, run `python3 test_hacheong.py` and
  `python3 -m unittest test_native_prompt.py test_hostcall_env.py test_record_paths.py test_red_gate.py test_tests_writer.py test_packaging.py`
  from this directory ([Self-check](README.md#self-check)); neither makes model calls.
  Use `python3 plugin/hacheong.py check` when editing member declarations. For documentation-only edits, check links and
  documented argv against the CLI and manifests. Follow [Versioning](README.md#versioning) when preparing a release.

## Developer setup

The project's agent environment is declared in `hunsu.json` and locked in `hunsu.lock.json`. Install those plugins at
the locked versions through the host's own plugin workflow. Call each engine at the root the lock names, never a glob
over the plugin cache; check with the installed hunsu engine's `check`. Never edit `hunsu.lock.json` by hand.
This project's own runs hire the installed, locked hacheong (`{plugin:hacheong}`), never the working `plugin/` here.
Work and run live checks on the selected, available host and on the worker hosts the lock declares for its roles;
those are the project's decision. Never launch or log in to another host to fill a checklist, and report coverage you
could not run as untested. Use `--by NAME` only for a person's word given for that judgment;
otherwise leave it out and the record signs as the session. Never put a person's name on a judgment they did not make,
and never report a check or a verification that did not run: no fake signatures.

Installing hacheong into another project exposes its skill and roles; it does not make this repository's maintainer
guidance that project's instructions.
