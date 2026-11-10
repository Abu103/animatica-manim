# Animatica session log (live, edit as you go)
Updated: 2026-11-10. Newest status on top. Any Claude session can resume from here.

## Context
- Repo: https://github.com/Abu103/animatica-manim (released v0.1.1 with tinytex-manim.zip asset, sha256 83fde080..., download verified + LaTeX compile verified from sandbox 2026-11-04)
- User runs on Windows, provider nim, model nvidia/nemotron-3.5-super-vl-120b-a12b
- Goal: stable demo to show others; then features that weak/free models (nemotron 120b, "3 super 550b") can drive reliably
## Status (2026-11-10, Hermes session, card B4c "make the tests fast")
- Branch: `hermes/b4-conformance-clean` (B4 + B4b + B4c), 19 commits on `main` (`0c0b444`). **Not pushed.**
- Changed (B4c, 7 commits): `src/animatica/backends/scheduler.py`, new `src/animatica/render_cache.py`, `src/animatica/conformance.py`, `scripts/ci_render_gate.py`, `scripts/ci_tests.py`, `tests/conftest.py`, `tests/test_conformance.py`, `tests/test_ci_gate.py`, new `tests/test_render_pool.py`, new `tests/test_render_cache.py`, new `tests/test_text_cache.py`, `.github/workflows/ci.yml`, `pyproject.toml`, `docs/HERMES_PLAYBOOK.md`, `docs/TASKS_FOR_HERMES_V02.md`.
- Measured on the owner's machine (i5-1135G7, 4 cores / 8 threads, 7.7 GB RAM, 20 GB free disk): full suite **369 s -> 156 s**; render gate **145 s -> 68 s cold / 1.9 s warm**; corpus renders per CI run **35 -> 18**. Worker count on that machine: 369 s serial, 183 s (-n 2), 154 s (-n 3), 155 s (-n 4), 138 s (-n 6).
- Root cause of the flaky geometry tests under `-n 4`: Manim caches every rendered text as an SVG under `<media_dir>/texts`, keyed by the text and the style but **not by the process**. Two workers that render the same string write the same file and one can read it half written. Proof: 8 processes rendering one string into one media directory -> `xml.etree.ElementTree.ParseError: no element found`. Fix: every process gets its own `media_dir` (`tests/conftest.py`).
- The conformance corpus is rendered **once** per CI run now, by the render gate, which also checks the scene count and the duration `expected.json` promises. The suite stopped rendering it (88 s of the 369 s for the same evidence).
- The render cache is keyed by the storyboard, the quality, the interpreter, the Manim version and a fingerprint of every source file in the package, so a changed component is never served from the cache. `ANIMATICA_NO_RENDER_CACHE=1` forces a real render.
- Verified: `python scripts/ci_tests.py` -> 934 passed, 4 failed, 0 skipped (the 4 are the pre-existing environment failures: `test_bootstrap_script.py` x3, `test_tex_path.py` x1). `python scripts/ci_render_gate.py` -> exit 0, `CLEAN: 18 storyboard(s) rendered within the allowlist`, twice (67.7 s cold, 1.9 s warm). The workflow YAML parses; every bash block in it passes `bash -n`.
- NOT verified: nothing is pushed and no CI has run on this branch. The CI LaTeX change (the 45 MB TinyTeX bundle instead of the 10m47s apt step) is **UNVERIFIED until the Linux job is green**: the bundle carries no `varwidth`, which `standalone.cls` requires, so the step installs it with `tlmgr` and then compiles a probe document; if the probe fails the step falls back to apt, so the job is never weaker than before. `tlmgr` is a symlink to `tlmgr.pl` and needs perl, which the ubuntu runner has.
- OPEN ITEM (found, not fixed): neither the Linux nor the Windows TinyTeX bundle carries `varwidth.sty`, and `doctor.py`'s `NEEDED_TEX_FILES` does not list it -- so `animatica doctor` reports LaTeX as OK while the equations silently degrade to plain text. The bundles are built by `.github/workflows/build-tinytex.yml` and `build-tinytex-windows.yml`.

## Status (2026-11-08, Hermes session, task cards T10 + T11 + T12 + T13)

## Status (2026-11-08, Hermes docs-lookup-skill session)
- Branch: hermes/docs-lookup-skill, off origin/main (c963c2b). No push.
- Created skills/external-docs-lookup/SKILL.md (external-docs-lookup skill, ~200 words, pack format).
- Created AGENTS.md with rule: before using/fixing a third-party API call you're unsure of, follow external-docs-lookup. (AGENTS.md did not exist on origin/main; created with this rule.)
- Created docs/HERMES_PLAYBOOK.md failure-mode table with row: guessed library behavior -> external-docs-lookup. (HERMES_PLAYBOOK.md did not exist on origin/main; created with this table.)
- Condition 4 research: Hermes config.yaml mcp_servers section (line 2553; schema command+args+timeout+connect_timeout for stdio, url+enabled for HTTP; doc reference website/docs/user-guide/features/mcp.md at line 1619). Active entries: mermaid (npx -y mcp-mermaid), deepwiki (http). Context7 (npx -y @upstash/context7-mcp) fits the stdio mermaid pattern -> supported. No config was edited (per instruction).
- Config change APPLIED (hermes config set): added `mcp_servers.context7` with `@upstash/context7-mcp@4.4.4`, `lazy: true`, `timeout: 120`, `connect_timeout: 60`. Backup: /tmp/config.yaml.before-context7.20261108-151459 and /tmp/config.yaml.before-mermaid-removal.20261108-163450 (kept, not deleted). YAML parsed OK after edit. `hermes mcp list` shows context7 ✓ enabled.
- ADVISORY MAL-2026-4147: `mcp-mermaid` (npm) has known malware advisories. Hermes' malware block caught it: `hermes mcp test mermaid` -> BLOCKED. Removed `mcp_servers.mermaid` from ~/.hermes/config.yaml via `hermes config unset mcp_servers.mermaid`. Backup kept at /tmp/config.yaml.before-mermaid-removal.20261108-163450. YAML parsed OK after removal. `mermaid` not installed, not run, not retried. `context7` and `deepwiki` remain untouched. `skills.external_dirs` untouched.

## Status (2026-11-08, Hermes session, task cards T10 + T11 + T12)
### T12 Windows TinyTeX bundle [Gate A, approved with conditions] - DONE, Windows VERIFIED by CI
- First-try pass: no (1 strike, fixed). Strikes: 1. Escalated: no.
- Branch: `hermes/t12-windows-tinytex` @ 1c176e9 (base `hermes/t11-version-truth`).
- Changed: new `.github/workflows/build-tinytex-windows.yml`, new `src/animatica/tex_bundle.py`, new `tests/test_tex_bundle.py` (15 tests), `src/animatica/doctor.py` (bundle path + `tinytex_bin_dirs`), `tests/test_doctor_fix.py` (+2 tests), `scripts/bootstrap.ps1`, `docs/NATIVE_DEPS.md`, `docs/SETUP.md`, CHANGELOG.md.
- Design: bundle first, upstream TinyTeX installer as fallback. Fails closed: with an empty sha256 constant the bundle is NOT downloaded at all. URL pinned to the explicit release tag (never "latest"), tag + sha256 kept as one constant pair. Hash verified on the downloaded file BEFORE unpacking; a mismatch deletes the file, logs one line and falls through. Env overrides `ANIMATICA_TEX_URL` / `ANIMATICA_TEX_SHA256` (an override URL alone does NOT bypass verification).
- Unpack: staged in a temp dir and moved into `<project>/.tex/` only when complete, so an interrupted unpack never looks installed. Zip entries that escape the target are rejected (two independent guards: a `..` pre-filter and a resolved-path check in the extraction loop). Layout normalised so `bin/windows` lands where `tinytex_bin_dirs` looks.
- RED proof: with the bundle call removed, both new doctor tests fail ("the prebuilt bundle must be tried" / "the upstream installer must run when the bundle failed"); with the hash check disabled, the mismatch test fails; with the zip-slip `..` filter disabled the in-loop guard still catches it (defence in depth, verified by hand).
- Verified: `python -m pytest -q tests/test_doctor_fix.py` -> 10 passed. `python scripts/ci_tests.py` -> 762 passed, 0 failed, 0 skipped, 0 errors, 0 warnings. `bootstrap.ps1` parses cleanly (checked with the Windows PowerShell parser via powershell.exe). The workflow YAML parses and defines 4 triggers + 11 steps. The Linux bundle path is untouched (`git diff --name-only` shows no change to build-tinytex.yml / tex-deps.yml / bootstrap.sh).
- STRIKE 1 (fixed): the first `build-tinytex-windows` run (42483454535) failed at "Install Animatica and verify the bundle path". Real log: `message: no known sha256 for the prebuilt bundle; using the upstream installer`. Cause: each `run:` block is a separate PowerShell process, so `$env:ANIMATICA_TEX_URL` / `$env:ANIMATICA_TEX_SHA256` set in one step did not reach the next. Fix: write both through `$GITHUB_ENV` (commit 1c176e9). The step now also fails fast when the override did not arrive.
- VERIFIED BY CI: run 42483719081 (`ci`) -> success; jobs linux / windows / hyperframes all success; linux and windows each report "762 passed, no skips, no warnings". Run 42483719068 (`build-tinytex-windows`) -> success on windows-latest; the job installed TinyTeX, compiled a probe equation, packed the bundle, computed the sha256, then downloaded that fresh artifact through Animatica with the env override, verified the hash, unpacked it and confirmed `latex.exe` and `dvisvgm.exe` under `.tex/bin/windows`. The Windows bundle path is therefore proven on a real Windows runner, not just unit-tested.
- OPEN ITEM (not part of T12): seed `WINDOWS_TEX_SHA256` in `src/animatica/tex_bundle.py` with the hash from the first successful `build-tinytex-windows.yml` run, and publish the `tex-deps-v1-windows` release with the asset. Until then the bundle is never used by a real user (fail closed).
- OPEN ITEM: the `tex-deps-v1-windows` release tag does not exist yet on GitHub; the release asset is published when a release event fires.

### T13 TUI keys with an Input focused [Gate A, approved] - DONE
- First-try pass: yes (after correcting the test to type into the focused Input before pressing ctrl+j; the empty-prompt case correctly rejects navigation). Strikes: 0. Escalated: no.
- Branch: `hermes/t13-tui-input-focus`.
- Changed: `src/animatica/tui.py`, `tests/test_tui.py` (+6 tests), `docs/TUI.md`, `docs/TASKS_FOR_HERMES_V02.md` (T13 card rewritten; stale Alt+Left/Alt+Right references removed).
- Root cause: `ctrl+j`/`ctrl+b` are app-level bindings, but Textual routes `ctrl+j` to a focused `Input` as `newline`/`submit`, so the navigation binding never fired while an Input owned the keyboard.
- Fix: `priority=True` on the `ctrl+j`/`ctrl+b` bindings plus a `_binding_blocked()` guard in `action_next_step`/`action_prev_step` that returns early when a modal screen is pushed (`len(screen_stack) > 1`) or a FilterSelect drop-down is open (`has_class("open")`). `priority=True` alone is not sufficient in Textual's `_check_bindings` (which runs with `priority=False`), so the guard is what keeps modals/pickers from being bypassed.
- Binding precedence verified under pytest on Linux: `python -m pytest -q tests/test_tui.py` -> 46 passed, 0 failed. Full gate: `python scripts/ci_tests.py` -> 768 passed, 0 failed, 0 skipped, 0 errors, 0 warnings.
- Real-terminal `ctrl+j` delivery UNVERIFIED on Windows (no Windows runner available here); fallback documented in docs/TUI.md: the visible Back/Continue buttons on the step navigation bar always work.
- grep for stale Alt+Left/Alt+Right references: none remain in docs/, README*, or src/.

### T10 Install the agent pack [trivial] - DONE
- First-try pass: yes. Strikes: 0. Escalated: no.
- Branch: `hermes/t10-agent-pack` @ 2607d11 (base `arena/b5effee8-animatica-manim`).
- Changed: AGENTS.md, docs/HERMES_PLAYBOOK.md, docs/TASKS_FOR_HERMES_V02.md, docs/handoffs/.gitkeep (new), .gitignore.
- `.hermes/` added to .gitignore; verified `docs/handoffs/` is NOT ignored (`git check-ignore -v docs/handoffs/x.md` -> exit 1).
- Verified: `git status` clean; the nine animatica-process skills load from ~/.hermes/skills/animatica-process/ (task-intake, git-branch-discipline, milestone-handoff, tdd-loop, verify-before-claiming used this session).
- NOT verified: `~/.hermes/config.yaml` has no `skills.external_dirs` yet, so the repo's own `skills/animatica/SKILL.md` is not visible to Hermes. Needs owner approval (config edit).

### T11 Version truth [Gate A, approved] - DONE
- First-try pass: yes. Strikes: 0. Escalated: no.
- Branch: `hermes/t11-version-truth` @ 31a250f (base `hermes/t10-agent-pack`).
- GitHub truth (read with `gh`): releases are `native-deps-v1`, `v0.1.1`, `v0.1.0`. v0.1.1 was published 2026-11-04T15:50:29Z with one asset, `tinytex-manim.zip` (118,007,458 bytes, sha256 83fde080e52cdd7209738fb0876e3ddd3d5f755c5fdea4e2bca4222d120ecbf8). The v0.1.1 tag's own pyproject.toml still said `version = "0.1.0"`, so the published `animatica --version` reported 0.1.0.
- Changed: pyproject.toml and src/animatica/__init__.py -> 0.2.0.dev0; CHANGELOG.md split into `## v0.1.1 (2026-11-04)` (26 bullets) and `## Unreleased` (14 bullets) on the real `git diff v0.1.1 HEAD -- CHANGELOG.md`; new tests/test_version.py (4 tests).
- RED proof: `AssertionError: 0.1.0 is not newer than the published v0.1.1`.
- Verified: `python -m pytest -q tests -k version` -> 10 passed, 735 deselected. `python scripts/ci_tests.py` -> 745 passed, 0 failed, 0 skipped, 0 errors, 0 warnings. `animatica --version` -> `animatica 0.2.0.dev0`.
- NOT verified: no tag or release was created (owner does that); the changelog split was checked by script, not by a human reading it end to end.
- Pushed: `hermes/t10-agent-pack` and `hermes/t11-version-truth` are on origin (owner approved the push).

### Hermes config change (owner approved, same session)
- `~/.hermes/config.yaml`: set `skills.external_dirs = [~/animatica-manim/skills]` via `hermes config set skills.external_dirs` (the patch tool refuses Hermes config files by design). Backup made first, but the tool's rewrite deleted it, so the pre-change diff could NOT be shown; the change was verified instead by `hermes config get skills.external_dirs` and by parsing the YAML.
- Confirmed: `hermes skills list` now shows `animatica` with source `external`, status `enabled` - the repo's own `skills/animatica/SKILL.md` is visible to Hermes.

## Status (2026-11-04, agent session)
- [x] P1.2 eval harness: `animatica eval --provider X` scores reference prompts (valid-first-try, retries, lint warnings, duration); src/animatica/eval.py + tests/test_eval.py 3/3
- [x] T4 table component (6x6 max, rows fade in; tests 4/4)
- [x] T1 number_line component (scaffolded via `animatica new-component`, params/duration/fallback + tests 4/4; render smoke test needs a manim machine)
- [x] Setup made one-command: `animatica bootstrap` + `animatica doctor --fix` now REALLY installs ffmpeg/TinyTeX/TeX packages (was a print-only message); tests/test_doctor_fix.py 5/5. Root cause of lost tokens in old sessions: fresh TinyTeX lacks standalone/babel-english/etc.
- [x] Fast full-quality setup (~25-40s): `scripts/bootstrap.sh` + `bootstrap.ps1` (parallel uv + pre-baked tinytex-manim.zip), `.github/workflows/build-tinytex.yml` bakes the zip, ffmpeg via imageio-ffmpeg wheel (doctor + encoder probe fall back to its bundled binary), imageio-ffmpeg added to deps
- [x] Setup COMPLETE: self-contained bootstrap.{sh,ps1} (auto-installs uv, parallel uv+TeX zip, doctor verify, fallback to doctor --fix); GUIDE.md fast path documented; ffmpeg via imageio-ffmpeg; CI bakes tinytex-manim.zip. Remaining manual step: set ANIMATICA_GH_REPO/URL. Private repos supported: scripts try ANIMATICA_TINYTEX_URL (signed), then `gh release download` (user gh login), then GITHUB_TOKEN API; else fall back to doctor --fix.
- [x] Setup docs: docs/SETUP.md documents env vars, bootstrap procedure, private-repo fetch order, fallbacks
- [x] T2 recursion_tree (fib call tree, repeated calls highlighted, 31-node cap; scaffolded via new-component; 8/8 tests; suite 239 passed)
- [x] T8 eval prompts (15, all components) + CI smoke workflow (.github/workflows/ci.yml)
- [x] T3 array_viz, T5 timeline, T6 compare done (suite 257 passed, 5 env-only failures)
- [x] P2 JSON-CLI agent tools: list-components / component-schema / validate / lint (tests/test_json_api.py 4/4; suite 261 passed)
- [x] P1.1 two-stage generation: `generate_storyboard_two_stage` (outline -> per-scene fill, each retried alone) + `--two-stage` flag on `animatica make`; tests/test_two_stage.py 4/4
- [x] Bug F fixed (scale note no longer collides with two-line captions) -- replayed in fresh sandbox
- [x] T9 `animatica new-component NAME` scaffold implemented (src/animatica/scaffold.py + CLI + tests/test_scaffold.py); e2e verified: scaffold number_line in a project copy -> registry lists 10 components, generated tests pass
- [x] Suite in this sandbox: 231 passed, 20 skipped, 5 failed -- all 5 are ModuleNotFoundError: manim (environment-only). Setup prod-verified: release zip downloaded, checksum matched, latex+dvisvgm+tlmgr present, test formula compiled to SVG.
- [x] Hermes handoff written: skills/animatica/SKILL.md + refreshed docs/TASKS_FOR_HERMES.md (T7, T9 marked done)

## Status
- [x] 1. Review user's out2/video.mp4 (fib to 15th term, real nemotron run) -- 5 scenes, 25s
- [x] 2. Read skills. brainstorming => ARCHITECTURAL path: write spec, get user approval BEFORE feature code. using-superpowers => announce skill use. brightdata search => bdata CLI not installed/authed + sandbox network locked, used web_search instead
- [x] 3. Feature plan written: docs/ROADMAP.md (spec, DRAFT) + docs/TASKS_FOR_HERMES.md (9 task cards)
- [~] 4. P0 APPROVED by user ('yeah'). Sub-tasks below
- [x] 5. Re-packaged zip with ROADMAP + TASKS_FOR_HERMES + this log in docs/

## Findings
out2 video (real nemotron run, user's machine):
- GOOD: LaTeX now renders properly; ball + running sums work; captions don't overlap; model used bounce_sequence.
- BUG A: bounce_sequence capped at 12 terms, request was 0..15 (16 terms) -> model split into 2 scenes; scene 2 restarts (pads 0..11 vanish, scale resets, starts at 144 with no 55+89). FIX: raise cap to 20, tell prompt to never split a sequence.
- BUG B: linear pad height: with max 610 / 55 the first ~8 pads are invisible slivers. FIX: `scale` param (linear|sqrt|log) on bounce_sequence + bar_chart, labels keep true values.
- BUG C: final bar_chart 'Growth of terms' bars 0,5 invisible, value labels collide with axis labels. FIX: min bar height + same scale param.
- BUG D: scene order odd (equation after the bounce, mid-video). Prompt: lead with title, then equation/definition, then demo, then summary.
- BUG E: redundant scenes (final bar chart repeats bounce). Prompt rule exists, weak model ignored it -> needs validator-side check (see roadmap: lint/repair).

## Resume instructions
1. unzip patched zip, `pip install -e .`, `animatica doctor`, `pytest -q`
2. Continue first unchecked item above.

## Gate
- Feature code is BLOCKED until user approves docs/ROADMAP.md (brainstorming hard gate). Bug fixes A-E also wait for a 'yes' on the short design in the roadmap.

## Next session start here
1. Ask user: approved ROADMAP? any cuts?
2. If yes: implement P0 A,B,C (bugs A-E), re-run `animatica make "...fibonacci 0 to 15th term" --provider nim` on user machine.
3. Then P1.1 two-stage generation and P1.2 eval harness.

## Decision log
- 2026-11-04 user goal: tool real people use (also counts for college/portfolio). Reorder P0 to: install in 3 commands on Windows, doctor fixes, demo gallery, reliable output on first try. Still waiting for explicit "yes" on ROADMAP before coding.

## P0 checklist (approved 2026-11-04, goal = tool real people use)
- [x] P0.1 bounce_sequence cap 12->20 + prompt: never split a sequence (bug A) DONE, rendered 16 terms ok
- [x] P0.2 `scale` auto|linear|sqrt|log via components/_scale.py on bounce_sequence + bar_chart, min height, on-screen note when not linear (bugs B, C) DONE. tests written
- [x] P0.3 storyboard/lint.py (merge split bounce scenes, drop repeat bar_chart, warn phantom ball), wired in pipeline for model output only. Bug D (order) handled by PROMPT rule only, not enforced in code. Tests: tests/test_scale_and_lint.py. DONE, 226 tests pass
- [x] P0.4 README rewritten (3-step install, tlmgr line, first no-key video, free provider list); doctor prints a tip when no AI provider set; setup wizard shows where to get free keys. NOT done: auto-install of TeX packages, Windows untested
- [x] P0.5 docs/gallery/ (fibonacci, pythagoras, sine, howto: json + mp4, fibonacci.gif used in README). Hand-written storyboards, labelled as such. Known: steps_list block sits off-centre
- [x] P0.6 226 tests pass, zip repackaged

## Open items after P0 (next session)
1. USER MUST: run the real prompt on their machine with the new zip; confirm one scene, 16 terms, no warnings. Report any lint notes shown.
2. Bug D (scene order) only prompt-enforced. If nemotron ignores it, add a lint rule (equation before first demo).
3. steps_list off-centre (cosmetic).
4. Windows clean-clone install untested. CI smoke test not written.
5. Then P1: two-stage generation, eval harness, frame lint, LLM-friendly validation errors (docs/ROADMAP.md).
6. A real free-provider default (OpenRouter/Ollama) is only documented, not auto-configured.
