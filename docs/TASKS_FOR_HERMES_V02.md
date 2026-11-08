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
## v0.3 (PROPOSALS, need owner approval and a Claude-written spec first)
- Narration: offline text-to-speech timed to captions (candidate: Piper; UNVERIFIED current licensing/availability). New `--narrate` flag; captions already exist as timing source.
- Components batch 2: choose 6-9 with the owner (examples: probability tree, venn, pie/donut, code diff, network/graph traversal, unit-circle). Each is one card using `animatica new-component`.
- Agent surface: publish `skills/animatica` to the Hermes skills hub path; MCP tool polish.
- HyperFrames: decide promote or keep experimental after seeing real demand.
- Not before 0.3: web UI, doc-to-video, research-backed prompts.
