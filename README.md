# hacheong (하청)

The subcontractor of the LLM-development era: the people a plan hires by role.

## Using hacheong

Requires **Python 3.11 or later**; `python3` must resolve to a supported interpreter.

```sh
claude plugin marketplace add guinjaaaaaaaaaaaaaaaaaaaaakeop/hacheong
claude plugin install hacheong@hacheong
```

Codex:

```sh
codex plugin marketplace add guinjaaaaaaaaaaaaaaaaaaaaakeop/hacheong
codex plugin add hacheong@hacheong
```

Only `plugin/` is installed. The members, CLI, validators and limits are documented in
[plugin/README.md](plugin/README.md), the README that is installed.

## Developing hacheong

`plugin/` is the payload and the single runtime source. The repository root holds AGENTS.md/CLAUDE.md,
the six self-check suites and test_packaging.py, hunsu.json/hunsu.lock.json/hunsu-judgments.json and the
products' records; none of that development material is installed.

Root `hacheong.py` and `worker.py` are compatibility entry points for old source-checkout invocations:
`python3 hacheong.py check` and `python3 worker.py ARGS` run the payload's modules. Imports through those
entry points also return the payload's modules.

See [AGENTS.md](AGENTS.md#developer-setup) for an agent's developer setup and maintainer rules. Codex discovers
repository guidance along its project path. [Codex guidance loading](https://learn.chatgpt.com/docs/agent-configuration/agents-md).
Claude Code's direct `AGENTS.md` support depends on version and settings; [CLAUDE.md](CLAUDE.md) contains only
`@AGENTS.md` as a compatibility import, so the maintainer rules still have one source. [Claude memory and imports](https://code.claude.com/docs/en/memory#share-one-file-with-other-coding-tools).
Neither file is installed: a project that installs hacheong gets plugin/ only.

## Self-check

`python3 test_hacheong.py` — members load and assemble, the host stream parses into an answer and nothing short of a
real one is `done`, each validator fires on a recorded case, project-local members and domains shadow the plugin's,
`new` scaffolds something `check` refuses until it is written, a sandbox's refusal recorded in a codex or Claude Code
stream is said as `lacked` (and a local failure, or a host that can, is not). No model calls.

`python3 -m unittest test_native_prompt.py test_hostcall_env.py test_record_paths.py test_red_gate.py test_tests_writer.py test_packaging.py` — the
`--prompt-only` environment, a child host's identity, the record-path rule, the red-before-build gate, the tests writer’s context, support and transcript gates, and the package layout and compatibility entry points.
`test_hacheong.py` does not run these suites; the self-check is both commands. No model calls.

`python3 plugin/hacheong.py check` — validate the shipped member declarations.

## Versioning

Semver, and a version names one content: every change to the source — code, role text, this README — bumps the version
in all three manifests (`plugin/plugin.json`, `plugin/.claude-plugin/plugin.json`, `plugin/.codex-plugin/plugin.json`) and the marketplace
entries before it is used anywhere. **patch**: behavior or wording, every interface unchanged. **minor**: a new
member, field, validator or domain; what exists keeps working. **major**: the request, the envelope, or `worker`
changes shape — or a supported Python or host version is dropped. 2.0.0 is such a release: it raised the manifests'
floor to `python >=3.11`, dropping 3.9 and 3.10.

### Release and adoption

Documentation and shared instruction edits also need a patch bump when interfaces stay unchanged.
Keep the version equal in `plugin/plugin.json`, `plugin/.claude-plugin/plugin.json`, `plugin/.codex-plugin/plugin.json`,
and `.claude-plugin/marketplace.json` (both `metadata.version` and this product's `plugins[].version`).
`.agents/plugins/marketplace.json` currently has no version field; verify its product name and source path,
but do not invent a version field there.

Before publication, run the relevant checks in **Self-check** for behavior changes; for documentation-only
changes, verify links, command examples, imports and manifest consistency, plus `git diff --check`.
Publish the checked commit using this repository's existing release convention. Publication does not update
consumer installations: update the plugin through the host's supported workflow, reconcile the consuming
project's declared environment and lock if managed, and start a new host session to apply the installation.
Report publication, project adoption and live-host verification separately. Refreshing a locally linked
plugin is not an update procedure for every remote installation.
