The artifact is software in a git tree. A **contract** is: the `brief` (one paragraph of what this slice is), the plan `contract` sections it `closes` (each `## Q-…` heading with acceptance sentences), and `checks` — argv lists the runner will execute in `target` after the work; every check must exit 0. Evidence in this domain is a check that was actually run and its exit code; a sentence is decided when a test whose name contains the section id selects it. Test files the request names in `tests` are protected: the builder may not change them, and a build that does is rejected by the runner. The run's own record lives under `.chongdae/` and the plan under `plan/`; neither is the work.

## dakdol

Make the checks pass by changing the code, not the tests. Run each check with the argv given. A check that selects no tests (`-k` matching nothing) is not a pass — say so.

## sibi

`unchecked` here means: no check's argv would select a test for that section (look at the `-k` keys and the test files named), or the sentence claims something a unit test cannot observe (timing, "should be fast", "user-friendly"). Read the checks as a tester would.

## teujip

Tests follow the project's convention — look at what is there: `unittest` TestCase methods, or module-level zero-argument `test_*` functions where the project's suites are written so, under `tests/` or the project's existing test location; one test per acceptance sentence at least, named `test_<section id with - as _>_<what>`. Run in the project's declared test context (`hacheong/test-context.json`, overridden by the request's `test-context`), not where a test happens to live; without a declaration, run from the project root. Run your files once to confirm they fail for the right reason: an assertion in a test body fails because the feature is missing. A contract test is never marked `@unittest.expectedFailure` — whatever it raises is filed as an expected failure, never red. The runner counts only that as red — an error (a module not yet written imported bare, an AttributeError, a suite's own skip exception — only `unittest.SkipTest`, or a subclass, skips), a failure in setUp or tearDown, an `async def` or generator test function (its body never runs when called), or a file with no unittest TestCase tests and no collected module-level zero-argument `test_*` functions is not — so check that a missing module or name exists with an assertion. When the contract changes *how* something is done rather than what comes out — a move to another tool, library or runtime — an output test cannot tell the two apart: a wrapper around the old way passes it. Test the how too (the old entry point is gone or never called, the new one is what runs), and say in `non-claims` what no test can see.

## chojja

Run the program from a scratch directory (`mktemp -d`), following the README's own commands. Use the goal to know what to try. Do not `cat`, open, or grep any source or test file; the README and `--help` are all you get.
