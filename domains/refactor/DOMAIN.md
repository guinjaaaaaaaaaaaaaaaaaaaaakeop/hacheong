The artifact is software in a git tree, as in the code domain — a **contract** is the `brief`, the `contract` sections it `closes` and the `checks`; evidence is a check actually run; the request's `tests` are protected. What is different: a refactoring changes **placement, not behavior and not explanation**. The program must do exactly what it did (the checks say so), and it must still say why it does it: every docstring, every comment and every public name that existed before exists after, moved with the code it explains. A refactoring that drops an explanation has changed the program's meaning for its next reader; a site's split of one file into five lost eleven docstrings and fifteen comments this way, and a second task had to put them back.

## dakdol

Move code; do not rewrite it. When a function or class moves to another file, its docstring and the comments inside and directly above it move with it, word for word. Keep every public name (a moved name is the same name in a new file; a renamed name is not a refactoring — say so in `decisions` if the contract asks for one). Keep the tests as they are: they are the contract's, and a refactoring that needs a test changed was not one. Before you answer, compare the tree with HEAD yourself: the set of `def`/`class` names, the number of docstrings and the number of comment lines — none may shrink. The runner checks the same three things and refuses an answer where any of them shrank.

## sibi

`undecided` here includes: a brief that says "split" or "extract" without saying where each part goes; a contract that says nothing about what must be preserved (the checks decide behavior, but who decides names, docstrings and comments?). `unchecked`: a refactoring whose checks are only the existing tests — the output's identity (a build that must be byte-identical, an API whose names must not change) needs a check of its own, or it is a hope.

## teujip

A refactoring's tests are already written: they are the tests that exist. Do not add structure tests that pin code placement (which file a function lives in) — placement is what the refactoring is free to change, and such a test fails the moment the work is done. If the contract names an identity to keep (byte-identical output, an unchanged public name list), write that as a test that compares against HEAD, not against a hand-copied expectation.

## chojja

Nothing should look different to you. Follow the README as before; if anything you did before the change now fails or reads differently, that is the finding — with the README sentence and what you saw.
