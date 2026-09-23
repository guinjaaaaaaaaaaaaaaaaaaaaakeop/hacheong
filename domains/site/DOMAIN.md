The artifact is a static site in a git tree: content files, a generator that turns them into pages, and the pages it writes (an output directory the host serves). Everything the code domain says holds — a **contract** is the `brief`, the `contract` sections it `closes` and the `checks`; evidence is a check actually run; the request's `tests` are protected. What is added: the product has two faces. The **author** writes content files and runs the generator as the README says; the **visitor** reads the generated pages. A sentence about what a page shows is decided by a test that builds a site in a temporary directory and reads the page, not by reading the generator.

## dakdol

The generator's output is part of the product: after a change, build, and let the tests read the pages. Do not hand-edit generated pages; change the generator or the content.

## sibi

A sentence about a page is `unchecked` unless a test builds and reads that page. "Looks right", "readable", "clean" are not observable: ask for the element, the text or the order that makes them so.

## teujip

Build a site from fixture content in a temporary directory, run the generator there, and read the generated files. Test what a visitor would see — the text, the links, the order, the attributes a script reads — not the generator's internals.

## chojja

You are both first users. As the **author**: copy the project to a scratch directory (`cp -R <target> "$(mktemp -d)"`), and there follow the README to write a post and build the site — never in the project itself. As the **visitor**: read the generated pages in that copy's output directory the way a browser would render them: what text appears, in what order, which links go where, what a button says. Reading a generated page — in your copy, or the pages already built in the project — is looking at the product; opening the generator, the tests or the content files' sources is not — do not. Report what did not work, what was unclear and what surprised you, each with the README sentence or the page text quoted.
