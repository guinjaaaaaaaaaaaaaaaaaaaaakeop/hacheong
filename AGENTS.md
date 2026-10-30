# Maintaining hacheong

This file governs work in this source repository. The installed hiring procedure has one source:
[skills/hire/SKILL.md](skills/hire/SKILL.md). Use that skill when hiring members; maintaining the plugin does not
itself call a member. See [README.md](README.md#shared-guidance-and-hosts) for host integration and CLI entry points.

- Keep member roles, answer schemas and policies in `members/`, domain guidance in `domains/`, and enforcement in
  `worker.py`. Preserve the request and answer envelopes when changing a validator.
- Keep `hostcall.py` self-contained; an installed plugin must not import another plugin's checkout.
- Keep the shared procedure in the skill. Host manifests and adapters carry host-specific settings, not a second
  copy of the workflow. Keep `CLAUDE.md` as the single `@AGENTS.md` import.
- For behavioral changes, run `python3 test_hacheong.py` from this directory; its self-check uses no model calls.
  Use `python3 hacheong.py check` when editing member declarations. For documentation-only edits, check links and
  documented argv against the CLI and manifests. Follow [Versioning](README.md#versioning) when preparing a release.

Installing hacheong into another project exposes its skill and roles; it does not make this repository's maintainer
guidance that project's instructions.
