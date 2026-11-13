# Sandbox bootstrap: one command, under 60 seconds, any network

Date: 2026-11-12 · Base: `main` @ `6329f6d` · Status: draft for owner review · Path: architectural

## 1. Problem and success criteria

An agent (Claude, Hermes on Nous models, others) starting in a bare sandbox
spends about 22 minutes on setup before it can run anything. The cost is
cairo/pango (no Linux wheels), resolving and installing manim and its
dependencies, and getting the repo itself. `scripts/bootstrap.sh` is built for a
person's machine: it tries apt, then a native bundle, then pip, and offers
LaTeX.

Done when, on a fresh container with only `curl`, `tar` and `sh`:

1. One command ends with `animatica doctor` passing and a one-frame smoke
   render written. No other step, no judgment calls.
2. The core install finishes in under 60 s on the **best** and **average** tiers
   and under 120 s on the **worst** tier. Per-phase timings are printed. These
   are targets to be measured (section 9), not promises.
3. Later code additions, changes and deletions need no rebuild of anything.
4. Dependency changes cannot leave the fast path silently stale.
5. Every failure degrades to the next fallback, never to a dead end, and the
   last fallback is today's `bootstrap.sh` unchanged.

Non-goals: Windows or macOS fast path (existing CI and `bootstrap.ps1` stay as
they are), GPU rendering, changing any component or render behavior.

## 2. Network tiers

| Tier | Reachable | Runtime source |
| --- | --- | --- |
| Best | GitHub, PyPI | release asset; PyPI available for repair |
| Average | GitHub incl. release CDN, no PyPI | release asset |
| Worst | `codeload.github.com` only | `runtime-<key>` branch via codeload, in parts |

All tiers fetch the same bytes. Only hosting differs.

## 3. The command

```sh
curl -fsSL https://codeload.github.com/Abu103/animatica-manim/tar.gz/refs/heads/main | tar xz && sh animatica-manim-main/scripts/sandbox.sh
```

`codeload` is used because it is the only host the worst tier reaches. Needs
`curl`, `tar`, `sh`. `ANIMATICA_REF` selects another branch or tag (the URL
ref changes too; `sandbox.sh` re-reads it from its own checkout).

## 4. Two layers

**Code layer: the repo, always live.** Fetched at the requested ref every run.
Wired in by a `.pth` file pointing at `src/`, never copied. Adding, changing or
deleting modules, components, tests or scripts needs no rebuild.
If `github.com` git is reachable the script replaces the extracted tree with
`git clone --depth 1`; otherwise it runs `git init`, sets `origin`, and makes one
local commit, so branches, commits and `git am` work with no Git access.

**Runtime layer: Python, wheels, native libs.** A relocatable directory holding
a standalone CPython (python-build-standalone), every pinned dependency from
`pyproject.toml` already installed, and the cairo/pango libs. The sandbox's own
Python, pip and apt are never used. Target: Linux x86_64, glibc 2.36 or newer
(the same floor as `docs/NATIVE_DEPS.md`).

Runtime key: `sha256(dependency list from pyproject.toml + python minor +
platform tag)`, shortened to 12 hex. The script computes it locally from the
fetched `pyproject.toml`, so the key is always the one the checked-out code
needs.

## 5. Fetch order and fallbacks

Each step has its own timeout; failure moves to the next step.

1. **Release asset** `animatica-runtime-<key>.tar.gz` (fastest). Gzip, because a bare sandbox cannot be assumed to have zstd.
2. **`runtime-<key>` branch via codeload**: `part-NN` files, each under 95 MB
   (GitHub file limit is 100 MB), joined and checked against `SHA256SUMS`. One
   branch per runtime, because a codeload branch tarball downloads the whole
   branch: a shared branch would pull every kept runtime. A tiny `runtime-latest`
   branch holds a `KEY` file naming the newest key.
3. **Key not published yet** (dependencies just changed, CI not finished): take
   the newest published runtime and, if PyPI is reachable, `pip install` only
   the difference.
4. **Same, no PyPI**: use the newest runtime with a loud warning listing the
   missing or mismatched packages; `animatica doctor` is run and its verdict
   printed, never hidden.
5. **No runtime reachable at all**: run `scripts/bootstrap.sh`, unchanged.

Integrity: every download is verified against a checksum before use. A bad
checksum is a failed step, not a warning.

## 6. Staying fresh (CI)

New workflow `.github/workflows/sandbox-runtime.yml`:

- Triggers on changes to `pyproject.toml`, the workflow itself, and a nightly
  schedule; also `workflow_dispatch`.
- Computes the key; skips if that release asset already exists.
- Builds the runtime in a `python:3.12-slim-bookworm` container (glibc 2.36),
  reusing the native build already in `native-deps.yml`, packs it, uploads the
  release asset, and force-pushes parts and `SHA256SUMS` to a fresh
  `runtime-<key>` branch (single commit) and updates `runtime-latest`.
- Keeps only the last 3 `runtime-*` branches.

Gate in `ci.yml`: a job fails the PR if the runtime key for the PR's
`pyproject.toml` has no published runtime **and** the PR does not trigger the
build workflow. Merging a dependency change therefore cannot leave the fast
path stale without someone seeing it.

## 7. Steps of `scripts/sandbox.sh`

1. Resolve ref and root; fetch or verify the code layer (section 4).
2. Compute the runtime key.
3. Fetch and unpack the runtime (section 5), into `<root>/.animatica-runtime/`.
4. Write `<root>/.animatica-env` (PATH, `LD_LIBRARY_PATH`, `PYTHONPATH`, the
   `.pth`) and an `animatica` shim. Agents run `. ./.animatica-env` in each new
   shell.
5. Verify: `animatica doctor`, then a one-frame smoke render. Tests that need
   LaTeX stay skipped until step 6.
6. Start the TeX layer download in the background (reusing `tex_bundle.py` and
   the existing `tex-deps.yml` bundle). `animatica doctor` reports "TeX: still
   downloading" or "ready". Not part of the 60 s budget.
7. Print per-phase timings and one final line: ready, degraded (with the
   reason), or failed (with the exact fallback tried). Exit non-zero if the
   core install exceeded its budget or `doctor` failed.

Flags: `--no-tex`, `--verify-only`, `--ref <ref>`, `--runtime-only`.

## 8. Agent entry point

The first lines of `AGENTS.md` become the one command and the activation line.
The existing rules in `AGENTS.md` are unchanged.

## 9. Testing and measurement

- `tests/test_sandbox_script.py`: key computation (stable, changes when a
  dependency changes, ignores unrelated edits), each fallback step selected when
  the previous one is forced to fail (local `file://` fixtures, no network),
  checksum failure rejected, `.pth` picks up an added and a deleted module.
- A CI job runs the command in a clean `debian:bookworm-slim` container with
  only `curl`, `tar`, `sh` installed and the network restricted to codeload,
  records per-phase times, and fails over budget. This is the evidence for the
  tier targets in section 1.
- Before the plan is final, measure the real compressed runtime size and the
  per-tier time. If the size forces more than about 6 parts on the worst tier,
  revisit trimming (strip tests, `.pyc` and unused scipy parts) before shipping.

## 10. Risks

- Runtime size is an estimate (about 150 to 250 MB compressed, unmeasured).
- glibc older than 2.36 sandboxes fall to fallback 5.
- The `runtime-*` branches are force-pushed; nothing else may live on them.
- python-build-standalone adds a third-party artifact; it is pinned by version
  and checksum in the workflow.
- A sandbox that blocks even `codeload` has no fast path; fallback 5 also fails
  there, by definition.

## 11. Out of scope

Replacing `bootstrap.sh`, Windows fast path, caching rendered output between
sessions, changing the TUI or setup wizard.
