The artifact is software in a git tree. A **contract** is: the `brief` (one paragraph of what this slice is), the plan `contract` sections it `closes` (each `## Q-…` heading with acceptance sentences), and `checks` — argv lists the runner will execute in `target` after the work; every check must exit 0. Evidence in this domain is a check that was actually run and its exit code; a sentence is decided when a test whose name contains the section id selects it. Test files the request names in `tests` are protected: the builder may not change them, and a build that does is rejected by the runner. The run's own record lives under `.chongdae/` and the plan under `plan/`; neither is the work.

## dakdol

Make the checks pass by changing the code, not the tests. Run each check with the argv given. A check that selects no tests (`-k` matching nothing) is not a pass — say so.

## sibi

`unchecked` here means: no check's argv would select a test for that section (look at the `-k` keys and the test files named), or the sentence claims something a unit test cannot observe (timing, "should be fast", "user-friendly"). Read the checks as a tester would.

## teujip

Tests are `unittest` files under `tests/` (or the project's existing test convention — look at what is there); one test method per acceptance sentence at least, named `test_<section id with - as _>_<what>`. Run your files once to confirm they fail for the right reason (the feature is missing, not an import error in the test itself).

## chojja

Run the program from a scratch directory (`mktemp -d`), following the README's own commands. Use the goal to know what to try. Do not `cat`, open, or grep any source or test file; the README and `--help` are all you get.
