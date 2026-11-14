# Task cards for Hermes: path to Animatica 0.2.0 (then 0.3.0)

Rules: `AGENTS.md` applies to every card. One card per session. Fresh session per card.
Integration branch: the one the owner names (currently `arena/b5effee8-animatica-manim` until PR #7 is merged; then `main`). Branch per card: `hermes/<id>-<slug>`.
Gate A = owner/Claude approves the plan before code. Gate B = Claude reviews the milestone before the next one starts.
Log every finished card in `docs/SESSION_TASKS.md` (date, card, first-try pass yes/no, strikes, result, unverified).

---
## M0 Housekeeping

### T10 Install the agent pack  [trivial, no Gate A]
Files: AGENTS.md, docs/HERMES_PLAYBOOK.md, docs/TASKS_FOR_HERMES_V02.md, .gitignore.
Steps: copy pack files (install.sh does this), add `.hermes/` and `docs/handoffs/` is NOT ignored (handoffs are committed), commit.
Accept: `git status` clean; Hermes answers "what are the non-negotiable rules for this repo?" with AGENTS.md rules.

### T11 Version truth  [Gate A]
Problem: `pyproject.toml` and `src/animatica/__init__.py` say 0.1.0; docs/SESSION_TASKS.md says a v0.1.1 release exists with `tinytex-manim.zip`.
Files: pyproject.toml, src/animatica/__init__.py, CHANGELOG.md.
Steps: `gh release list` and `gh release view v0.1.1` to find the truth; report; propose the next dev version (`0.2.0.dev0`); a test asserting both version strings match.
Accept: `python -m pytest -q tests -k version` passes; report lists what GitHub actually shows.

---
## M1 Reliability

### T12 Windows TinyTeX bundle  [Gate A, NORMAL]
Why: Windows installs depend on the upstream TinyTeX download, which returned HTTP 504 in CI run #58. The existing prebuilt bundle (`.github/workflows/build-tinytex.yml`) is built on Ubuntu with `install-unx.sh` and cannot serve Windows.
Files: new `.github/workflows/build-tinytex-windows.yml`; `src/animatica/doctor.py`; `scripts/bootstrap.ps1`; `tests/test_doctor_fix.py`; `docs/NATIVE_DEPS.md` (or SETUP.md).
Steps: (1) read how doctor.py currently installs TinyTeX on Windows (it already retries the official installer 3 times). (2) Add a windows-latest workflow that installs TinyTeX, runs `tlmgr install standalone preview babel-english amsmath amsfonts dvisvgm xkeyval`, zips the tree, uploads as a release asset with a sha256. (3) doctor.py/bootstrap.ps1: try the asset first (verify checksum), then the upstream installer. (4) Unit tests with mocked download: success, bad checksum, 404 falls back, retries bounded.
Accept: `python -m pytest -q tests/test_doctor_fix.py` passes. Windows behavior: UNVERIFIED until the Windows CI job is green; say so.
Do not: change the Linux bundle; push; publish a release.

### T13 TUI keys with an Input focused  [Gate A]
Problem: `ctrl+j` (continue) and `ctrl+b` (back) did not change steps while an
`Input` widget had keyboard focus — Textual routes `ctrl+j` to the focused
`Input` as `newline`/`submit`, so the app-level navigation binding never fired.
The bindings themselves are correct (`ctrl+j` / `ctrl+b`); docs/TUI.md already
documents them. The fix makes the app bindings win over a focused Input, while
opting out when a modal screen or an open picker drop-down owns the keyboard.
Files: src/animatica/tui.py, docs/TUI.md, tests/test_tui.py.
Steps: (1) add `priority=True` to the `ctrl+j`/`ctrl+b` bindings in
`src/animatica/tui.py`. (2) Guard `action_next_step`/`action_prev_step` so they
return early when a modal screen is pushed or a FilterSelect drop-down is open.
(3) Add tests: navigation with an Input focused, typing still inserts
characters, no navigation while a modal or picker is active, no-op on the first
and last pane. (4) Confirm docs/TUI.md lists `ctrl+j`/`ctrl+b` (it does; no
Alt+arrow references remain).
Accept: new tests pass; `python -m pytest -q tests/test_tui.py`; follow
`cross-platform-tui-tests`. Real-terminal `ctrl+j` delivery is UNVERIFIED on
Windows; the documented fallback is the Back/Continue buttons.

### T14 Graph legend and x-axis ticks vs caption  [Gate A]
Problem: owner ran "explain taylor series" and saw a missing graph legend and x-axis tick labels overlapping the caption. `components/graph.py` already builds a legend for two curves and leaves headroom above the caption band, so first find the case that fails.
Files: src/animatica/components/graph.py, tests/test_graph*.py (create if missing), docs/COMPONENTS.md only if params change.
Steps: (1) generate or hand-write the storyboard that reproduces it (Taylor series with a function and its approximations); save it as `tests/conformance/graph_taylor.json`. (2) Render a preview frame on a manim machine: `animatica make --from tests/conformance/graph_taylor.json -o /tmp/g --quality preview`, then `animatica preview`. Look at the frame. (3) Write a geometry test that fails: legend present when >=2 series; tick-label bbox does not intersect the caption region. (4) Fix.
Accept: geometry test passes; frame re-rendered and described honestly; `python scripts/ci_tests.py` passes. Render check needs a manim machine; mark UNVERIFIED otherwise.

**Gate B (M1):** Claude reviews the three diffs and the Windows CI run before M2 starts.
**Gate B (M1.5):** You perform the T12b release and seed commit yourself before M2 starts.

---
## M1.5 — T12b: publish the Windows TeX bundle, seed the hash, lock the tag
[Gate A for the seed commit only; runbook you must execute yourself]

This card is a runbook for you. It ships the verified artifact, seeds the checksum, and defines the tag rule. Nothing here publishes or pushes on its own; you perform the tag, release, and seed commit yourself.

### 1. Why the workflow must skip on re-publish
T12's Windows bundle is built on `windows-latest` from whatever TinyTeX the upstream installer fetches that day: it is **not** reproducible. A release event rebuilds the tree and uploads a fresh `tinytex-manim-win.zip` with a **different sha256** than the verified artifact from run 42483719068. Without a guard, the workflow would silently replace the published bundle.

**Fix applied:** `.github/workflows/build-tinytex-windows.yml` now checks the asset name against the release's own tag (`github.event.release.tag_name`, not the old `RELEASE_TAG` env var, which would match the wrong release). If the asset already exists on that tag, the publish step is skipped and a `Keep the existing release asset` step prints the guidance below. The workflow publishes a fresh asset only when the release does not yet carry it.

**Which path I chose and why:** publish-after-publish is rejected, because a rebuilt zip's hash cannot be predicted and the seeded constant (below) is what makes the bundle path live at all. The workflow always tries to publish the new zip; only if the asset is already present does it keep that existing one. Publishing a new tag with a new pair is unconditional.

### 2. Immutability (optional, for you to decide later — NOT a step here)
Per GitHub's docs ("About releases", immutable releases section): when the repository setting `immutable_releases` is enabled, **Git tags associated with a release cannot be modified or deleted, and release assets cannot be modified or deleted. Immutability is enforced only after a release is published. Draft releases can be modified or deleted, and the associated git tags can be modified or deleted as well.**

The repo's `immutable_releases` setting is currently `null`, and the existing releases (`v0.1.0`, `v0.1.1`, `native-deps-v1`) all report `immutable: false`.

**Do not enable this in T12b.** It is an optional later decision for you, and you should know its consequence before choosing: turning it on would lock the tags and assets of every published release — including v0.1.0, v0.1.1 and native-deps-v1, whose `tinytex-manim.zip` users have already downloaded. You would not be able to re-upload or retag a locked asset, so a later build of the Windows bundle that changed its sha256 could not update v0.1.1's asset. The T12b card below states how it stays open rather than taking the setting for you.

### 3. Tag rule: a changed zip means a new tag, never a re-upload
The published zip is a build artifact: its sha256 changes whenever the upstream TinyTeX installer fetches a newer set of packages. A different zip **always** means a **new tag** (`tex-deps-v2-windows`, `tex-deps-v3-windows`, … and a new `tag + sha256` pair).

- The tag name is part of the URL the bundle is fetched from, and the checksummed file must match the tag's asset.
- Never re-upload to an existing tag, and never re-publish the same zip under a new tag: the existing one is preserved and the new pair is published.
- The workflow's release trigger implements this: it publishes a new asset only when the target release does not yet carry it, and prints the `Keep the existing release asset` guidance otherwise.

### 4. Seed the checksum, as a separate commit after you publish
Run it only after the T12 PR is merged, because the workflow file must exist on `main` for the release trigger to work.

Pre-flight (merge-base check):
1. `git fetch origin` and set `SHA=$(git rev-parse origin/main)`.
2. Verify the guard commit is in main: `git merge-base --is-ancestor e87215c "$SHA" && echo OK`. If it does not print OK, STOP.

3. Download and verify the artifact locally:
   ```
   mkdir -p /tmp/t12b
   gh run download 42483719068 --name tinytex-manim-win --dir /tmp/t12b
   sha256sum /tmp/t12b/tinytex-manim-win.zip     # must print e3e92c824cef9d0340e81d1bbecbef522a53582b77269e4dfbe5fe7e9c2463e3, else STOP
   cat /tmp/t12b/tinytex-manim-win.zip.sha256
   ```
   The download command and the pre-upload hash check are required: if the digest doesn't match `e3e92c824cef9d0340e81d1bbecbef522a53582b77269e4dfbe5fe7e9c2463e3`, do not proceed.
4. Create a **draft** release so the asset already exists when the release trigger fires (no race with the workflow's publish step):
   ```
   gh release create tex-deps-v1-windows --draft --target "$SHA" --latest=false \
     --title "Native deps v1 (Windows TinyTeX)" \
     --notes "Prebuilt TinyTeX for Windows, used by bootstrap.ps1/doctor. sha256 e3e92c824cef9d0340e81d1bbecbef522a53582b77269e4dfbe5fe7e9c2463e3. Built by workflow run 42483719068 (branch hermes/t12-windows-tinytex), verified by installing through Animatica." \
     /tmp/t12b/tinytex-manim-win.zip /tmp/t12b/tinytex-manim-win.zip.sha256
   ```
   Notes: `--draft` (publishes only when you later call `gh release edit --draft=false`), `--latest=false` (don't displace v0.1.1 as Latest), no `--verify-tag` (the tag doesn't exist yet on the remote; `--target` creates it at publish). Provenance note in the release notes says the asset was built on `hermes/t12-windows-tinytex`, not main — acceptable because you verified it end to end, but stated for transparency.
5. Publish the draft:
   ```
   gh release edit tex-deps-v1-windows --draft=false
   ```
6. **The runbook stops if the digests differ** — compare the published digest to the expected:
   ```
   gh release view tex-deps-v1-windows --json assets | jq -r '.assets[] | select(.name == "tinytex-manim-win.zip") | .digest'
   ```
   The output must equal `sha256:e3e92c824cef9d0340e81d1bbecbef522a53582b77269e4dfbe5fe7e9c2463e3`. If it doesn't, rollback:
   ```
   gh release delete tex-deps-v1-windows --cleanup-tag --yes
   ```
   Nothing has been seeded yet, so no user is affected and rollback is safe.
7. Seed the checksum in a **separate commit** on a new branch, pushed through a PR (not directly to main):
   - create the branch, set `WINDOWS_TEX_SHA256` in `src/animatica/tex_bundle.py` to the digest from step 5, commit, push, open a PR.
   - CI runs CI on the branch; once green and reviewed, merge to main.
   Verify with the unit tests (`tests/test_tex_bundle.py`): the constant is 64 lowercase hex characters, the tag+hash are the single pair that the URL derives from, and changing the tag changes the URL. The digest comparison itself is a runbook step, not a unit test: the tests can only check the shape of the constant, because they cannot see GitHub.

### 5. First real test of the live path (after the seed PR merges)
Once the seed PR runs CI, the Windows job runs `bootstrap.ps1` end to end. Because the fallback to the upstream installer is silent, that job could go green without using the bundle. **Open the Windows job log and confirm it says it installed from the bundle.** If no such log line exists, tell Hermes to add one first — without it you can't tell the two paths apart.

**Pre-flight workflow check** (before you publish):
```
grep -nE "types:|clobber|release upload|tag_name|RELEASE_TAG" .github/workflows/build-tinytex-windows.yml
```
The trigger should be `release`/`published` only, there must be no `--clobber`, and the asset-exists check should use `github.event.release.tag_name`.

### 6. Tests for this card (offline only)
- `tests/test_tex_bundle.py`: the constant is 64 lowercase hex characters; the tag+hash are the single pair the URL derives (tag in the URL, URL ends with the asset name, no "latest" ref, URL built from the tag so a changed tag changes the URL).
- All tests run offline. There is no network call in `test_tex_bundle.py`: the digest comparison is deliberately a runbook step, because a unit test cannot observe GitHub.

### Acceptance
- `python -m pytest -q tests/test_tex_bundle.py` passes (offline; new tests added: pair identity, tag-follows-URL, 64-hex shape).
- Runbook steps 1–6 complete by you; the seed commit is made after you publish, from the published asset's digest, and the runbook stops if the digests differ.
- **No release and no tag until you approve this updated card.**

---
---

## M1.6 — B4c: make the tests fast  [NORMAL; the owner's card, 2026-11-10]

Why: the suite cost six minutes and the render gate two and a half, and the
same conformance corpus was rendered twice per CI run. The owner asked for
speed first. Measured on the owner's machine (4 cores / 8 threads, 7.7 GB RAM):

| what | before | after |
|---|---|---|
| full suite | 369 s | ~150 s (4 workers) |
| render gate | 145 s | 64 s cold / 2 s warm (cached) |
| corpus renders per CI run | 35 | 18 |

Files: `src/animatica/backends/scheduler.py`, new `src/animatica/render_cache.py`,
`src/animatica/conformance.py`, `scripts/ci_render_gate.py`, `scripts/ci_tests.py`,
`tests/conftest.py`, `tests/test_conformance.py`, `tests/test_ci_gate.py`,
new `tests/test_render_pool.py`, new `tests/test_render_cache.py`,
`.github/workflows/ci.yml`, `pyproject.toml`, `docs/HERMES_PLAYBOOK.md`.

Steps:
1. RED: the timeline geometry tests fail at random under `-n 4`. Cause: Manim
   caches every rendered text as an SVG under `<media_dir>/texts`, keyed by the
   text and the style but **not by the process**; two workers that render the
   same string write the same file and one reads it half written. Proof:
   `race_probe.py` -> `ParseError: no element found`. Fix: every process gets
   its own `media_dir` (`tests/conftest.py`).
2. A render pool: `run_in_parallel()` + `render_workers()` (cores and free
   memory) in `backends/scheduler.py`; the gate renders the corpus in parallel.
3. The suite stops rendering the corpus; the gate takes it over and also
   checks the promised scene count and duration from `expected.json`.
4. A content-addressed render cache: the storyboard, the quality, the
   interpreter, the Manim version and a fingerprint of every source file.
5. The suite runs on four workers (`pytest-xdist`), with the worker count
   capped by the cores and the memory.
6. CI: the 10m47s apt step becomes the project's own 45 MB TinyTeX bundle
   (with a verified apt fallback), and the Windows job runs the gate too.

Accept: `python scripts/ci_tests.py` clean; `python scripts/ci_render_gate.py`
clean; the numbers in the table above.

---

---

## M1.7 — B4d: the recursion tree drew the wrong edges  [NORMAL; the owner's card, 2026-11-10]

Why: the frame `b4_recursion_tree.png` showed a call tree that was not one.
The left fib(3) had four edges instead of two, and they reached into the
branches of other parents. The gate and the tests reported nothing.

Files: `src/animatica/components/recursion_tree.py`, `tests/geometry.py`,
`tests/test_recursion_tree.py`.

Steps:
1. First the "before" evidence: render `tests/conformance/recursion_tree.json`
   on origin/main (before B4) and save the frames at the beat's end. Report
   whether the edges were already wrong there.
2. RED with real mobjects at 1280x720 and 1920x1080 for fib(5): for every
   edge, its start lies on/near the parent node's bbox (inflate 0.2u) and its
   end near the child node's bbox, and no edge touches any node that is not
   its parent or child.
3. Root cause: which commit introduced the mismatch, and why.
4. Fix at the root; the timing and safe-area tests keep passing.
5. Frames at 0.5 s, mid-beat and the final frame of the beat.
6. The same check as a generic helper in `tests/geometry.py`, so the other
   tree-like components can reuse it.

Accept: the frames show a call tree whose edges only ever run from a node to
its own child; the suite and the gate are clean.

---

---

## M1.8 — B4e: the recursion tree's video was longer than its beat  [NORMAL; the owner's card, 2026-11-10]

Why: the final frame of the recursion tree was missing 2 of its 14 edges, and
the tree was drawn from the leaves up.

Files: `src/animatica/components/_draw.py`, `src/animatica/components/recursion_tree.py`,
`src/animatica/components/array_viz.py`, `src/animatica/frame_lint.py`,
`src/animatica/pipeline.py`, `tests/test_recursion_tree.py`, `tests/test_array_viz.py`,
`tests/test_frame_lint.py`.

Steps:
1. RED: the beat must not overrun its declared duration in the video, the whole
   tree must be on screen before the fade-out, and the tree must be drawn from
   the root down.
2. Find the cause: Manim writes ceil(run_time * fps) frames per animation, so
   a run time that is not a whole number of frames makes the video longer than
   the beat. The tree has 29 animations; the rounding added up to 0.6s.
3. Fix at the root: the Clock counts in frames and the tree budgets in them.
4. Frames: 0.5 s, mid-beat, and the hold before the fade-out.
5. array_viz: the title at the top of the frame, centred, the boxes below it.
6. frame_lint: the caption strip is derived from the caption band, not a
   constant.

Accept: the video is as long as the beat declares, the hold frame shows all
14 edges, the tree grows from the root, and the suite and the gate are clean.

---

---

## M1.9 — B4f: the LaTeX packages are complete  [NORMAL; the owner's card, 2026-11-10]

Why: neither TinyTeX bundle carries `varwidth.sty`, and `standalone.cls` loads
it for its border box. Every formula therefore failed to compile and the
equations degraded to plain text -- while `animatica doctor` reported LaTeX as
fine, because the doctor only compiles a formula with `--deep`.

Files: `src/animatica/doctor.py`, `scripts/bootstrap.sh`,
`.github/workflows/build-tinytex.yml`, `.github/workflows/build-tinytex-windows.yml`,
`tests/test_doctor_fix.py`.

Steps:
1. `varwidth` goes into `TEX_PACKAGES` and `NEEDED_TEX_FILES`, so `doctor --fix`
   installs it and the check can see it.
2. On Linux the doctor leaves the packages to apt -- but the one-line installer
   unpacks a TinyTeX bundle, which only tlmgr can complete. The doctor has to
   recognise that tree.
3. The installer completes the bundle after unpacking it, with the doctor's own
   package list.
4. The bundle workflows install `varwidth` too, so the next bundle is complete.

Accept: the doctor repairs a bundle on Linux, leaves the system TeX Live to
apt, and the package lists carry varwidth.

---

## M2 Evidence (this is the portfolio differentiator)

### T15 Reference prompt set  [trivial]
Files: tests/reference_prompts.txt (currently 31 lines; check it, do not clobber).
Steps: ensure >=30 diverse prompts covering every component at least once, one per line, no code. Remove duplicates.
Accept: `python -m pytest -q tests/test_eval.py` passes; a test asserts every registered component is covered by name or obvious intent.

### T16 Eval baseline run  [NORMAL; uses free providers, rate limits apply]
Files: docs/EVAL_BASELINE.md (new). No source changes.
Steps: with the owner's providers configured (`animatica setup`), run `animatica eval --models <providerA>,<providerB> --prompts tests/reference_prompts.txt --max-retries 2`. Paste the real table into the doc with date, commit sha, provider, model id, and the label LIVE-MODEL OUTPUT. Never fabricate or round numbers; if a run hits rate limits, record that and the partial result.
Accept: doc exists, every number traceable to a pasted run.

### T17 Offline regression gate  [Gate A, NORMAL]
Idea: deterministic CI check that storyboard validation/lint scores do not regress, with no network.
Files: tests/test_eval_gate.py, tests/fixtures/eval_replay/*.json (recorded storyboards), src/animatica/eval.py only if a hook is needed.
Steps: record 10 provider outputs once (from T16 runs) as fixtures; the test replays them through validate+lint+score and asserts minimum thresholds stored in a small JSON.
Accept: test passes offline; deleting a field in a fixture makes it fail (prove it).

**Gate B (M2).**

---
## M3 Showcase

### T18 Render the gallery  [NORMAL, needs a manim machine (owner's WSL)]
Files: scripts/render_gallery.py (new), docs/GALLERY.md (new). Do not commit MP4s.
Steps: script loops `docs/gallery/*.json`, runs `animatica make --from <f> -o out/gallery/<name> --quality preview`, writes a results table (ok/warnings/time). Owner attaches MP4s to a release later.
Accept: script exits non-zero if any render fails; table pasted from a real run; warnings listed verbatim.

### T19 Verified installs table  [trivial, owner runs it]
Files: docs/VERIFIED_INSTALLS.md.
Steps: create the table (OS, date, commit, method, result, notes). Only rows from real clean-machine runs of the README one-liner. Leave the table empty until the owner reports a run.
Accept: file exists; no invented rows.

### T20 README demo  [trivial]
Files: README.md. Add a short "what you get" section linking docs/GALLERY.md and EVAL_BASELINE.md. No claims beyond verified results. Verify every link resolves before committing.

**Gate B (M3).**

---
## M4 Release 0.2.0
Use skill `animatica-release`. Cards: T21 changelog, T22 version bump, T23 release notes draft. The owner performs the tag and release.

---
## v0.3 (APPROVED by the owner, 2026-11-14)
- **Narration: approved.** Spec: `docs/superpowers/specs/2026-11-14-narration-design.md`
  (licensing resolved, sync strategy = extend beat to `max(visual, narration)`,
  default voice lazy-fetched, `--voice` ships in 0.3 default-only). Next: T26
  implementation card off this spec.
- **Components batch 2: approved, all 6 of the listed examples** (no new ones
  substituted): probability tree, venn, pie/donut, code diff, network/graph
  traversal, unit-circle. One card per component via `animatica new-component`,
  cards T27-T32.
- **Agent surface: approved.** Publish `skills/animatica` to the Hermes skills
  hub path; MCP tool polish. Card T33.
- **HyperFrames: keep experimental.** No real-demand signal yet to promote it;
  revisit when one shows up rather than on a schedule. Not a card.
- Not before 0.3 (unchanged): web UI, doc-to-video, research-backed prompts.
