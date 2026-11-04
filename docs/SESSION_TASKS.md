# Animatica session log (live, edit as you go)
Updated: 2026-11-04. Newest status on top. Any Claude session can resume from here.

## Context
- Repo: https://github.com/Abu103/animatica-manim (released v0.1.1 with tinytex-manim.zip asset, sha256 83fde080..., download verified + LaTeX compile verified from sandbox 2026-11-04)
- User runs on Windows, provider nim, model nvidia/nemotron-3.5-super-vl-120b-a12b
- Goal: stable demo to show others; then features that weak/free models (nemotron 120b, "3 super 550b") can drive reliably

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

