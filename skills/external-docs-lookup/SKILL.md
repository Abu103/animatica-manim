---
name: external-docs-lookup
description: Use when behavior of a third-party library is unclear, a library call fails, or you are about to guess a signature or option.
version: 1.0.0
---
# External docs lookup

## When to Use
Before using or fixing a third-party library call whose behavior you are unsure of — a library call fails, an API signature is unclear, or you would otherwise guess an option or flag.

## Procedure
Order — stop at the first source that answers the question:

1. **Pinned version.** Run `pip show <pkg>` or check pyproject.toml / lock file. Always note the pinned version.
2. **Installed source (ground truth for this version).** `python -c "import X; print(X.__file__)"`, then grep and read the specific function. Use `python -m pydoc X.Y` for signatures.
3. **Official docs for that version**, via web fetch. Known sites: textual.textualize.io, docs.manim.community, typer.tiangolo.com, docs.pytest.org, docs.python.org, docs.github.com. Pick the pinned version if the site is versioned. Check the changelog for breaking changes between the pinned and latest versions.
4. **Context7 MCP**, only if configured. Pin the package to a version at least 14 days old (`@upstash/context7-mcp@4.4.4`, not latest), set `lazy: true`, and verify with `hermes mcp test context7` before using. Resolve the library id (`resolve-library-id`), then fetch docs for one narrow topic (`query-docs`). Context7 queries contain only a library name and a narrow topic, never private code or secrets. See `references/context7-mcp.md` for the exact config.
5. **Library issues or source at the pinned tag.**

## Rules
- Never guess a signature.
- If sources disagree, the installed source wins.
- Blog posts and Stack Overflow are hints only — verify them against source.
- Read the one relevant function or page, not whole files or crawls.
- Log `docs checked: <source, version>` in the handoff.
- The two-strike rule still applies: a lookup does not reset the strike count.

## Verification
You can name the package version, the source that answered the question, and the exact function or page read.
