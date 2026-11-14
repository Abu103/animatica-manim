# Animatica session log (live, edit as you go)
Updated: 2026-11-14. Newest status on top. "Not pushed" in an entry means as of when it was written; `gh pr list --state all` is the source of truth for what merged. Any Claude session can resume from here.

## Status (2026-11-14, Claude session, card T26c "doctor check + lazy voice-model fetch")
- Branch: `hermes/t26c-on-real-main` off `origin/main` @ `b643764` (T26b merged as #55 -- by the time this card finished, the owner had merged it, so this patch is rebased onto the real thing rather than my locally-applied copy). **Not pushed**; delivered as a patch. Over the ~150-line guideline (254 lines across 4 files) -- flagging per rule 10 rather than letting it pass quietly; stayed at 4 files, the extra length is the new `tests/test_narration_fetch.py` (7 tests) plus two added `test_doctor.py` tests.
- `narration.py`: `piper_binary_path()`/`voice_model_file()` (cache locations under `config_dir()/narration`), `fetch_piper()` (downloads+verifies the real Piper v1.2.0 Linux binary against a sha256 I computed myself in this session from a live download -- **verified**) and `fetch_voice_model()` (downloads+verifies a voice model against `VOICE_MODEL_SHA256`, fails closed on an unknown voice or hash mismatch, never fetches unverified). Both reuse `tex_bundle.download`/`sha256_file` rather than duplicating them.
- **Caveat, stated plainly rather than buried**: `VOICE_MODEL_SHA256[DEFAULT_VOICE]` was read off the model's own Hugging Face LFS record via a web search (the page itself states its SHA256), not hashed from a file I downloaded and verified myself -- `huggingface.co` is not reachable from this sandbox (confirmed live: `curl` to it fails DNS resolution). This is **unverified** in the strict sense of rule 5; flagged in the module's own docstring/comment too so it isn't lost. The Piper binary hash, by contrast, **is** verified: I downloaded the real `v1.2.0` `piper_amd64.tar.gz` from `github.com/rhasspy/piper` in this session and hashed it myself.
- `doctor.py`: new `narration` check in `run_checks()` (reports `piper=yes/no voice=yes/no`, same shape as the `latex` check); `fix_dependencies()` now calls `fetch_piper()`/`fetch_voice_model()` when missing, each wrapped so a failure is reported and does not abort the rest of `--fix`.
- **Ran `animatica doctor --fix --yes` for real** (not just the tests) in this sandbox: `fetch_piper()` succeeded end-to-end -- downloaded, hash-verified, extracted, and the resulting binary runs (`piper --help` exits 0). `fetch_voice_model()` failed closed exactly as designed, with a clear message, when `huggingface.co` could not be reached -- it did not fall back to silence or crash the rest of `--fix`. This is the expected, honest outcome in a sandbox without Hugging Face access; a machine with normal internet access should complete both fetches.
- Verified: `pytest tests/test_narration_fetch.py tests/test_doctor.py tests/test_narration.py tests/test_beat_durations.py` (30 passed); together with `test_pipeline.py`, `test_caption.py`, `test_cache.py`, `test_frame_lint.py`, `test_tex_bundle.py`: 132 passed, 8 skipped (pre-existing dvisvgm gap). `ruff check` on all four changed files: clean. Full `pytest tests/` run: 13 failures, confirmed **pre-existing** on `hermes/t26b-narration-sync` before this card's changes too (stashed and reran the same 13 -- identical) -- `test_graph.py`/`test_caption_room.py` (rendering-resolution-dependent), `test_sandbox_script.py`, `test_scheduler.py` (`cpus == 3` assumes a specific sandbox core count); none touch narration or doctor.
- NOT run: the full `scripts/ci_tests.py` strict gate (same `dvisvgm` gap as every prior card this session).
- Not started: T26d (`--narrate`/`--voice` CLI flag + the synthesize -> render -> mux sequence, wiring `narrate_storyboard`/`fetch_voice_model` into `make_video`), T27-T32 (components batch 2), T33 (agent surface).

## Status (2026-11-14, Claude session, card T26b "narration duration sync")
- Branch: `hermes/t26b-narration-sync` off `main` @ `4e8fa29` (T26, #54, already merged). **Not pushed**; delivered as a patch.
- `narration.py`: `wav_duration_seconds(path)` -- reads a WAV's real frame count and rate via the stdlib `wave` module, never assumed.
- `pipeline.py`: `_beat_durations()` takes an optional `narration_durations` (same nested per-scene-per-beat shape as `narrate_storyboard`'s output) and takes `max(visual, narration)` per beat, per the spec's section 3 decision. A beat with no corresponding narration entry, or a shorter list, keeps its visual duration -- and with `narration_durations=None` (the default) the function's output is unchanged from before this card.
- Still not wired into `make_video` or the CLI -- that's T26c (doctor check + lazy voice-model fetch) and T26d (`--narrate`/`--voice` flag + the actual synthesize-then-render-then-mux sequence + ffmpeg mux). This card only gives `_beat_durations` the capability; nothing calls it with real narration data yet.
- Verified: `pytest tests/test_beat_durations.py` (5 passed); together with `test_narration.py`, `test_pipeline.py`, `test_caption.py`, `test_cache.py`, `test_frame_lint.py`: 96 passed, 8 skipped (all 8 skips are the pre-existing "needs manim + latex + dvisvgm + ffmpeg" sandbox gap from T26's session, unrelated to this change); `ruff check` on all three changed files, clean. Patch applies clean and its tests pass against the real pushed `main` (checked by cloning fresh).
- NOT run: the full `scripts/ci_tests.py` gate, same `dvisvgm`-missing reason as T26.

## Status (2026-11-14, Claude session, card T26 "narration core module")
- Branch: `hermes/t26-narration-core` off `hermes/t25-v03-approvals`. **Not pushed**; delivered as a patch.
- Scope, deliberately narrowed from the full narration spec (AGENTS.md rule 10): just the core module, no pipeline wiring, no mux, no doctor check, no CLI flag. Those are separate cards (T26b sync wiring, T26c doctor check + voice fetch, T26d CLI flag + ffmpeg mux) so each stays reviewable on its own.
- `src/animatica/narration.py`: `synthesize()` (Piper via injected `run`/`which`, the same DI convention as `latex_check.probe_latex`/`doctor.run_checks`; fails closed with `NarrationUnavailable` on an unchecked voice, missing `piper`, missing voice model, or a non-zero Piper exit -- never falls back to silence) and `narrate_storyboard()` (one WAV per beat, same nested shape as `pipeline._beat_durations`).
- `pipeline.py`: extracted `beat_text()` (was inline in `_write_captions`) so the caption and the narration text can never drift apart, per the spec's section 4 instruction.
- Over the ~150-line guideline (261 lines across 3 files) -- flagging per rule 10 rather than letting it pass quietly. Stayed at 3 files; the extra length is almost all `tests/test_narration.py` covering each fail-closed path (unchecked voice, no piper, no model file, piper non-zero exit) plus the two `beat_text` paths, which felt worth keeping together rather than splitting a 9-test file across two cards.
- Verified: `pytest tests/test_narration.py -q` (9 passed), `pytest tests/test_narration.py tests/test_caption.py tests/test_cache.py -q` (37 passed, no regressions from the `pipeline.py` refactor), `ruff check` on all three changed files (clean), `animatica doctor` (unaffected by this change; `latex` already failed in this fresh sandbox before it -- `dvisvgm` is not installed here -- not something this card touched or can fix).
- NOT verified / not run: `python scripts/ci_tests.py` (the strict, zero-skip full gate) -- this sandbox is missing `dvisvgm`, so the full suite cannot currently pass here regardless of this change; ran the targeted and adjacent test files instead and read their output. No real Piper binary was available or used; every `synthesize()` test injects a fake `run`/`which`.

## Status (2026-11-14, Claude session, card T25 "v0.3 owner approvals")
- Branch: `hermes/t25-v03-approvals` off `hermes/t24-narration-spec` (429b2f3). **Not pushed**; delivered as a patch.
- Owner approved all of `docs/TASKS_FOR_HERMES_V02.md`'s v0.3 proposals in this session: narration, components batch 2 (all 6 listed examples, no substitutions), agent surface publish. HyperFrames stays experimental (no real-demand signal to promote on).
- Resolved the narration spec's two open owner questions (section 5): default voice is lazy-fetched on first `--narrate`/`doctor --fix`, not bundled into `sandbox.sh`/`bootstrap.*` (keeps the under-a-minute install promise); `--voice` ships in 0.3, default-only allowlist until a second voice's license is checked.
- Not started: T26 (narration implementation) and T27-T33 (components batch 2, agent surface). These are the next cards, one branch each per AGENTS.md rule 7.

## Status (2026-11-14, Claude session, v0.3 kickoff: narration spec)
- Branch: `hermes/t24-narration-spec` off `main` @ a54a93b. **Not pushed**; delivered as a patch.
- `docs/superpowers/specs/2026-11-14-narration-design.md`: resolves the licensing UNVERIFIED flag on `v0.3`'s narration proposal. Piper engine is MIT; voice models carry their own per-voice license (checked against the real `rhasspy/piper-voices` MODEL_CARDs, not reseller marketing pages, which overstate the restriction). `en_US-ljspeech-medium` (public domain) recommended as the default bundled voice.
- Spec's real content is the sync-strategy decision (section 3): extend a beat to `max(visual_duration, narration_duration)` rather than time-stretching either side, reusing the per-beat text `_write_captions` already computes.
- Two open questions left for the owner (section 5): default-voice bundle size vs lazy fetch, and whether `--voice` ships in 0.3 or stays default-only.
- Not started: implementation (this is the "Claude-written spec" the roadmap asked for before any v0.3 code). Components batch 2 and the HyperFrames decision still need the owner's picks before those get their own cards.

## Status (2026-11-14, Claude session, cards T21-T23 "0.2.0 release prep")
- Branch: `hermes/t21-23-release-0.2.0` off `main` (a224414+63035bd, i.e. after C4/C5 merged as #50/#51). **Not pushed**; delivered as a patch.
- **T22 (version bump):** `0.2.0.dev0` -> `0.2.0` in `pyproject.toml` and `src/animatica/__init__.py`. `tests/test_version.py` (4 tests, no heavy deps needed) run for real and pass: matches, valid PEP 440, past the published `v0.1.1`.
- **T21 (changelog):** renamed `## Unreleased (0.2.0.dev0)` to `## v0.2.0 (2026-11-14)`, added the two entries that section was missing (C4 TinyTeX-cache-path fix #50, C5 windows CI split #51), and opened a fresh empty `## Unreleased` section above it for whatever lands next.
- **T23 (release notes draft):** `docs/RELEASE_NOTES_0.2.0.md`, written for a release page (highlights + fixes-worth-knowing + upgrading + known gaps) rather than as a changelog diff. Marked draft at the top; owner edits before pasting into the GitHub release.
- Not done: the tag and the release itself (owner's step, per the task card).

## Status (2026-11-14, Claude session, card C5 "windows CI split")
- Branch: `hermes/c5-windows-ci-split` off `hermes/c4-windows-tex-cache`. **Not pushed**; delivered as a patch.
- Problem: the single `windows` job was taking >4 min and bottlenecking every CI run, same shape `linux` had before `linux-tests`/`linux-render` split it.
- Split `windows` into `windows-tests` (bootstrap, doctor, the full pytest suite with `--durations=25`) and `windows-render` (bootstrap, bundle-visibility doctor, smoke test, fixture render gate, the PowerShell-parses check) that now run in parallel. `windows` itself is now a cheap `ubuntu-24.04` aggregate — same `needs: [...] / if: always()` pattern as `linux` — so branch protection still waits on one check name.
- TinyTeX cache: both halves restore the same key; only `windows-tests` saves it, to avoid two jobs racing to save the same cache entry.
- `windows-render` drops the `uv pip install -e ".[dev,tui]"` step: `ci_smoke.py`/`ci_render_gate.py` only touch base deps (`av`, `manim`, ...), which `bootstrap.ps1` already installs. That, plus not re-running the full suite there, is most of the expected wall-clock win.
- Added 5 RED tests to `tests/test_ci_gate.py` (`test_windows_is_an_aggregate_of_two_halves` and friends) before the split, confirmed red, then made them pass; also re-ran `test_aggregate_linux_job_is_untouched` as a regression check.
- Verified by hand-running the same `_ci_job()` regex logic the new tests use against the edited `ci.yml` (all 5 assertions pass) and `yaml.safe_load` on the file. **Not verified**: an actual Windows runner — `manim`'s `pangocairo` system dependency isn't installable in this container, so the real `pytest tests/test_ci_gate.py -k windows` run and the first live `windows-tests`/`windows-render` CI run after merge are still open. Read that first run for the actual wall-clock before vs after, and for "Cache saved" on `windows-tests` / a restore hit on the next run.

## Status (2026-11-14, Claude session, card C4 "PR triage and branch cleanup")
- Branch: `hermes/c4-windows-tex-cache`. **Not pushed**; delivered as a patch.
- Done by the owner from the commands given: PRs #48 (C1 + C2) and #49 (C3) merged; 23 remote branches whose PRs were merged deleted (every one from `gh pr list --state merged`, none with an open PR). That list included `hermes/c31-caption-duplicate`, so the C3 note that its PR was unidentified is now settled: it was merged.
- **#38 (`steps_list` caption room, #30): close.** `main` already has the identical code in `steps_list.py` and the `KNOWN_VIOLATORS` entry is gone (#42/#43).
- **#40 (`ci/apt-cache-linux`): close, one change kept here.** Its apt-cache commit is #39, already merged. Its remaining change moves the Windows TinyTeX cache path from `.tex` to `%LOCALAPPDATA%\Animatica\tex`, which is where `tex_bundle.install_windows_bundle` unpacks the bundle (per-user dir first, `.tex` only as the fallback), so the job has been caching a directory that stays empty. This card applies the path fix only. #40 also changed the save condition from main-only to "not a pull request"; not taken, since every branch push would write a new cache entry per run.
- Verified: the path against `src/animatica/tex_bundle.py` (`user_data_tex_dir`) and `scripts/bootstrap.ps1`; `ci.yml` diff is two lines. NOT verified: the cache actually saves and restores; the save step only runs on `main`, so read the first `windows` run after merge for "Cache saved" and a restore hit on the next one. The `C:\Users\runneradmin` path assumes GitHub-hosted Windows runners.

## Status (2026-11-14, Claude session, card C3 "docs cleanup")
- Branch: `hermes/c-minor-docs` (the minor PR; C1 + C2 are in the major PR `hermes/c-major-lint-ffmpeg`, by the owner's request). **Not pushed**; delivered as a patch.
- Changed (docs only): `CHANGELOG.md` (new Unreleased section: sandbox setup, lint gate, ffmpeg fix, caption/graph/compare fixes, CI split; later eval items that sat under v0.1.1 moved up), this log (stale "Not pushed" lines now name the PR that merged them; #46, #34, #26, #19; `c31-caption-duplicate` left unmatched), `docs/superpowers/plans/2026-11-12-sandbox-bootstrap.md` (36 boxes ticked, status note), its spec (draft -> implemented), `docs/ROADMAP.md` and `AGENTS.md` (no longer "DRAFT").
- Judgement call to confirm: the ROADMAP is now labelled the working plan, based on the log's own "P0 APPROVED by user" line and the T-cards built since. Revert that one header if you do not want to say so.
- Verified: every ticked step has a test in `tests/test_sandbox_script.py` or `tests/test_ci_gate.py` (Task 5 under slightly different names); `pytest tests/test_sandbox_script.py tests/test_version.py` -> 70 passed, 1 failed (the same one that fails on `main`).
- NOT done (needs push access): C4, triaging PRs #38 and #40 and deleting merged remote branches. The PR numbers in the log came from `git log` titles, not the GitHub API (it refused this session).

## Status (2026-11-14, Claude session, card C2 "ffmpeg without the bundled native libs")
- Branch: `hermes/c-major-lint-ffmpeg` (C1 + C2 in one PR, by the owner's request), off `main` = `7e231ae`. **Not pushed**; delivered as a patch.
- Changed: `src/animatica/_nativelibs.py` (new `system_tool_env()`), `backends/scheduler.py` (concat), `encode/transcode.py`, `encode/probe.py` (all three ffmpeg calls), `tests/test_nativelibs_env.py` (new), this log. 6 files.
- **Bug**: `.animatica-env` and `_nativelibs.ensure()` put `<runtime>/native/lib` on `LD_LIBRARY_PATH` for the `manim` child. A system `ffmpeg` inherits it, loads the bundle's glib instead of its own and dies with a symbol lookup error (exit 127), so a two-scene render failed at the concat step.
- **Evidence (RED)**: 10 new tests failed (`system_tool_env` missing; ffmpeg calls passed no `env`). End to end: with a broken library in the bundle dir on `LD_LIBRARY_PATH`, `concat_videos` on `main` raised `ffmpeg concat failed (exit 127)`.
- **Fix**: `system_tool_env()` returns a copy of the environment with only the bundle directory removed from `LD_LIBRARY_PATH` (other entries kept; the variable is dropped when empty; `os.environ` untouched). Every ffmpeg call (concat, transcode, `-version`, `-encoders`, test encode) passes it as `env=`. The `manim` child still gets the bundle.
- Verified (this session, Linux): `pytest tests/test_nativelibs_env.py tests/test_probe.py tests/test_transcode.py tests/test_scheduler.py` -> 49 passed, 1 failed (`test_system_info_cpus_and_memory`, a 2-CPU sandbox, fails the same on `main`). Same poisoned-bundle `concat_videos` call: `main` exit 127, branch succeeded (7905-byte output).
- `tests/test_sandbox_script.py`: 66 passed, 1 failed (`test_added_module_importable_and_deleted_module_gone_without_rebuild`); the identical failure is on untouched `main` in this sandbox, cause not investigated.
- Not fixed on purpose: `.animatica-env` still exports `LD_LIBRARY_PATH` to the user's shell, because running `manim` by hand needs it. A system `ffmpeg` typed directly in that shell can still hit the bug; the pipeline cannot.
- NOT verified: the full suite (the sandbox had no manim/dvisvgm); Windows (`LD_LIBRARY_PATH` is a no-op there); CI on GitHub.

## Status (2026-11-14, Claude session, card C1 "a lint gate for real defects")
- Branch: `hermes/c1-lint-defects` (PR #47); folded into `hermes/c-major-lint-ffmpeg` with C2.
- Changed: `pyproject.toml` (ruff config, `ruff` in the `dev` extra), `.github/workflows/ci.yml` (one lint step in `linux-tests`), 51 source, test and script files for the fixes below (20 in `src`, 30 in `tests`, 1 in `scripts`), `docs/SESSION_TASKS.md`. This is far over the 5-file card limit because most of those files are one-line unused-import removals.
- **Evidence (RED)**: `ruff check src scripts tests --select F,E9` found **110 defects** on `main`: 88 unused imports, 12 unused variables, 4 f-strings without placeholders, 4 undefined names, 2 redefinitions. (`experiments/` has 11 more; it is excluded on purpose, the pilots are self-contained.)
- **Fix**: the 110 are gone, and CI now fails on any new one (`python -m ruff check src scripts tests`, rules `F` and `E9` only; no style rules).
  - `ai/repair.py`: `Scene` was used in annotations and never imported; the mid-file imports moved to the top and the `_VE` alias is gone.
  - `tui.py`: `ComposeResult` is a `TYPE_CHECKING` import now, not a lazily-built dict entry.
  - `cli.py edit`: five locals "snapshotting originals for rollback" were never read (the comment described a rollback that works on files, not on these); removed with the comment.
  - `manim_backend.py` `colors`, `bar_chart.py`/`bounce_sequence.py` `top`, `eval.py` `eventual`: assigned, never used; removed.
  - **Four tests in `test_pipeline.py` guarded nothing**: they patched `pipeline.ManimBackend`, a name production code no longer reads (backends come from `default_backends()`). Autofix removing that dead import exposed it. They now patch `animatica.backends.ManimBackend`, where it is really instantiated.
  - `test_capability.py::test_compatible_capabilities_pass` was `assert True` ("placeholder"); deleted, the registry-based test after it is the real one. Two unused assignments in `test_doctor_fix.py` / `test_eval.py` dropped.
- Verified (this session, Linux sandbox from `scripts/sandbox.sh`): `ruff check src scripts tests` -> All checks passed. `pytest -n 4` on the branch: **13 failed, 1283 passed, 40 skipped, 2 errors**; on untouched `main`: 13 failed, 1284 passed, 2 errors. The failed/error set is **identical** (diffed); the one fewer pass is the deleted placeholder. `ANIMATICA_NO_RENDER_CACHE=1 python scripts/ci_render_gate.py` -> `CLEAN: 20 storyboard(s) rendered within the allowlist`.
- The 15 failures are the sandbox, not the code: no `dvisvgm` (graph and caption-room tests, 10 of them), a 2-CPU box where `test_system_info_cpus_and_memory` expects 3, and the system ffmpeg at an absolute path (2 `test_backend_base` errors, 1 `test_doctor_fix`).
- **FOUND, not fixed (next card)**: `scripts/sandbox.sh` writes `LD_LIBRARY_PATH=<runtime>/native/lib` into `.animatica-env`, and every child process inherits it. The system `ffmpeg` then dies with `symbol lookup error: libgdk_pixbuf-2.0.so.0: undefined symbol: g_task_set_static_name`, so a two-scene render fails at the concat step with exit 127 inside the sandbox. Proof: the same binary runs with `env -u LD_LIBRARY_PATH`. The render gate was run through a wrapper that unsets it.
- NOT verified: the 40 render-marked tests did not run (no `dvisvgm`); the lint step in `ci.yml` has not run on GitHub; nothing was run on Windows.

## Status (2026-11-13, Claude session, card "parametric_graph: a circle is a circle, and labels stay readable")
- Branch: `hermes/parametric-shape`, stacked on `hermes/eval-model-flag`. Merged into `main` with PR #46 (`7e231ae`).
- Changed: `src/animatica/components/parametric_graph.py`, `tests/test_parametric_graph.py`, `docs/SESSION_TASKS.md`.
- **Problem (noticed while fixing #32)**: the axes were always 10 x 5 units, so one unit along x was twice as long as one along y; `cos t, sin t` was drawn as an ellipse (measured curve width/height = 2.00). The circle also passes through the axis numbers at +-1, and the curve was drawn over them.
- **Fix**: `_axes_lengths()` gives the largest equal-scale plot that fits the 10 x 5 box; if that would leave a side under 2.0 units (a very wide, flat curve) the axes fill the box with independent scales as before. Axis numbers get a higher z-index than the curve and a background-colour halo (stroke width 6), so a curve crossing a label does not hide it.
- Tests (6 new, 34 in the file): `_axes_lengths` keeps equal scales and stays inside the box (4 cases), falls back for a flat curve; render tests: the circle's width/height is 1.00 +- 0.02, and every label the curve really crosses is above the curve and has a halo (the test first checks that a crossing exists). RED on the old source: width/height 2.000 and `label -1.0 is under the curve`. GREEN: 34 passed.
- Frame checked by eye (`animatica make --from` the Parametric Circle storyboard, preview quality): a round circle, the crossed `1.0` / `-1.0` labels legible.
- Verified on Linux with dvisvgm: `test_caption_room.py`, `test_conformance.py`, `test_parametric_graph.py`, `test_ci_gate.py`, `test_graph.py` -> 178 passed.
- **The price**: an equal-scale circle is 5 x 5 units, so on the slide it is smaller than the old 10 x 5 ellipse.
- NOT verified: `ci_render_gate.py` and the full suite were not run on this branch; nothing was run on Windows.

## Status (2026-11-13, Claude session, card "eval: a model per provider, and defaults that still exist")
- Branch: `hermes/eval-model-flag`, stacked on `hermes/windows-test-env`. Merged into `main` with PR #46 (`7e231ae`).
- Changed: `src/animatica/cli.py`, `src/animatica/ai/router.py`, `src/animatica/ai/groq.py`, `src/animatica/ai/openrouter.py`, `src/animatica/ai/providers.toml`, `tests/test_provider_defaults.py` (new), `docs/SESSION_TASKS.md`.
- **Problem (found in T16)**: `animatica eval` had no way to give two providers two model ids (one `ANIMATICA_MODEL` for the process), and two defaults were retired: Groq shut `llama-3.1-8b-instant` down for free and developer keys on 2026-08-16 (Groq's deprecation page names `openai/gpt-oss-20b` as the replacement), and the OpenRouter default `meta-llama/llama-3.1-8b-instruct:free` was unavailable.
- **Fix**: `get_provider(name, config, model=None)`; `animatica eval --provider X --model M`; `--models nim,groq:openai/gpt-oss-20b` (`provider:model`, split on the first `:` so `:free` ids work); the same provider listed twice is an error (the table has one column per provider); an unknown provider is a clean `Error:` line, not a traceback. New defaults: groq `openai/gpt-oss-20b`; openrouter `nvidia/nemotron-3.5-super-vl:free` (id as shown on openrouter.ai; the free list changes every few days, so `--model` is the way to override).
- Tests: `tests/test_provider_defaults.py`, 12 tests. RED on the old source: 7 failed; GREEN on the new source: 12 passed. Code defaults equal `providers.toml`, no default is a retired id, the OpenRouter default ends in `:free`.
- Verified on Linux: `-m "not render"` run stopped at 2 failures in `test_caption_room.py` / `test_graph.py` that also fail on unmodified `main` in this sandbox (no `dvisvgm`, so no axis numbers); they are not in files this change touches.
- NOT verified: no live call to Groq or OpenRouter (no keys here), so the two new default ids are checked against the providers' published pages only, not by a request.

## Status (2026-11-13, Claude session, card "the four Windows-only test failures")
- Branch: `hermes/windows-test-env`, off `main` = `ff7cc06`. Merged into `main` as PR #46 (`7e231ae`).
- Changed: `tests/test_bootstrap_script.py`, `tests/test_tex_path.py`, `docs/SESSION_TASKS.md`. **No source change.**
- **Cause, from the owner's Windows run**: (1) `bash` on PATH was `C:\Windows\system32\bash.EXE`, the WSL launcher; it answers `--version` but cannot open a `C:\...` script path (`No such file or directory`, exit 127), so 3 tests in `test_bootstrap_script.py` failed. (2) `test_dir_without_latex_is_not_accepted` found the machine's real `C:/tools/tinytex/bin/windows` (a fixed candidate in `tinytex_bin_dirs`) and returned it instead of `None`.
- **Fix**: `_usable_bash()` now tries Git for Windows' bash first (next to the `git` found on PATH, then the default folders), and accepts a candidate only if it also parses the real script (`bash -n <script>`). The tex test patches `tinytex_bin_dirs` to the temp dir only, so no installed TinyTeX can decide it. New test: a shell that answers `--version` but cannot open the script is rejected.
- Verified on Linux: `tests/test_bootstrap_script.py` + `tests/test_tex_path.py` -> 49 passed (was 48 + the new test).
- NOT verified: on Windows. The failure itself cannot be reproduced on Linux (no WSL launcher, no `C:/tools/tinytex`); the owner's run is the evidence. Run `python scripts/ci_tests.py` on Windows: the expected result is 0 failed.

## Status (2026-11-11, Hermes session, card "dynamic worker count for pytest (-n) and the render gate")
- Branch: `hermes/m2-eval-baseline` (off `main` = `88652e2`). Merged as PR #34 (`e43d00f`). No new branch created; this completes the owner's in-progress worker-count rework left in the working tree.
- Changed: `src/animatica/backends/scheduler.py`, `scripts/ci_tests.py`, `scripts/ci_render_gate.py`, `tests/test_scheduler.py`, `docs/SETUP.md`.
- `system_info()` returns (usable CPUs, total RAM): affinity then cgroup `cpu.max` quota on Linux, else `os.cpu_count()`; `/proc/meminfo` on Linux, `GlobalMemoryStatusEx` via ctypes on Windows, `sysctl hw.memsize` on macOS; unknown -> None (memory limit skipped).
- `pick_workers(kind, cpus, mem_gb)`: workers = min(cpus, floor(mem_gb / 1.5)), raised to min 4, never above memory limit when below 4 (then max(2, limit)), capped at 12. `kind="test"` uses 1.5 GB/worker; `kind="render"` keeps its budget (free memory, cap 4). `ANIMATICA_TEST_JOBS` / `ANIMATICA_RENDER_JOBS` override everything (invalid values ignored with a warning). Returns (workers, limit in {cpu, mem, cap, env}).
- `ci_tests.py` prints `workers: N (cpus=..., mem=...GB, limit=...)` first and passes `-n N`; the gate prints the same line.
- Tests (pure, injected cpus/mem, no machine probing): 2/8->4, 4/16->4, 8/16->8, 16/8->5, 32/64->12 (cap), 2/2->2 (memory forbids 4); affinity smaller than cpu_count; cgroup "200000 100000" -> 2 cpus; env override wins; garbage env ignored with warning; mem unknown -> cpu/cap rules only; render keeps its budget. `tests/test_scheduler.py`: 23 passed.
- Verified (raw output): `ANIMATICA_TEST_JOBS=4 python scripts/ci_tests.py` -> workers 4, wall 317s, 0 skips. Dynamic default run 1 -> workers 5 (cpus=8, mem=7.7GB, limit=mem), wall 202s, 0 skips. Dynamic default run 2 -> workers 5, wall 270s, 0 skips. Both dynamic runs: 1037 passed, 0 skipped. (The 4 failures in every run are pre-existing Windows environment failures: `test_bootstrap_script.py` x3 needs bash, `test_tex_path.py` x1 needs TinyTeX -- they fail on a clean checkout too and are unrelated to this change.)
- `tests/test_ci_gate.py` + `tests/test_render_pool.py`: pass.
- NOT verified: a fully clean `python scripts/ci_tests.py` on this Windows box (the 4 pre-existing env failures block "CLEAN"); no CI has run; the gate's `-n` path was not exercised end-to-end (it needs real Manim renders).
- Handoff: none needed; this is not a milestone end.

## Context
- Repo: https://github.com/Abu103/animatica-manim (released v0.1.1 with tinytex-manim.zip asset, sha256 83fde080..., download verified + LaTeX compile verified from sandbox 2026-11-04)
- User runs on Windows, provider nim, model nvidia/nemotron-3.5-super-vl-120b-a12b
- Goal: stable demo to show others; then features that weak/free models (nemotron 120b, "3 super 550b") can drive reliably
## Status (2026-11-11, Hermes session, card C31 "a caption wider than the frame is drawn twice")
- Branch: `hermes/c31-caption-duplicate`, off `main` = `88652e2`. Written before it was pushed; the PR is not identified here (`gh pr list --state all --head hermes/c31-caption-duplicate`).
- Changed: `src/animatica/components/_draw.py`, `tests/test_caption.py`, `docs/SESSION_TASKS.md`. **No other source change.**
- **The evidence** (the card asks for it before the fix): rendered the storyboard of issue #31 on `main` at `--quality preview` (the Fibonacci bounce with the 88-character caption) -> the caption's first line is printed twice, a few pixels off, over the caption itself. Frames: `out/c31_before.png` (before) and `out/c31_after.png` (after).
- **What is duplicated -- measured, not guessed**:
  - The caption **mobject** is NOT duplicated: `make_caption()` returns one `Text` with 72 glyph paths for the 72 non-space characters, no two glyphs at the same place, and the scene holds exactly one caption mobject.
  - `wrap()`'s output is NOT joined twice: the caption's SVG holds one `<use>` element per character (88 for 88 characters).
  - So the copy appears only in the **render**. Measured trigger: a caption of **two or more lines whose rendered baseline pitch is under ~0.75 units** is drawn twice. A one-line caption is never affected; a two-line caption narrower than the frame (the pitch stays 0.77) is fine; the same caption scaled down to the frame width (the pitch shrinks to 0.55) doubles -- and it doubles again when it is built at a smaller font instead of scaled (the pitch shrinks the same way).
  - The mechanism inside Manim is **not** understood -- the mobject, the SVG and the animation cache are all clean -- so the fix works around the measured trigger instead of the cause.
- **The fix** (`components/_draw.py`): the caption is built as **one Text per line** (the file's own docstring always said "one Text per line"), the lines are put on their own baselines, and the leading is an **absolute distance in the frame** (`CAPTION_LINE_LEADING = 0.85`) instead of a fraction of the font size, so scaling a caption down to fit the width no longer shrinks its leading into the range where Manim draws it twice.
- **The effective font size**: the caption's font is 40 (the cap) and a caption that has to fit the frame width is scaled to 12.8/17.8 = 0.72 of it, so its effective font size is **28.8 -- below `MIN_FONT_SIZE` (32)**. It is still **one copy** of the text, which is what the card requires.
- **The price**: the leading no longer shrinks with the caption, so a two-line caption is 1.15 units tall instead of 0.85 (the content above it loses 0.3 units) and its lines sit 0.5 units apart instead of 0.23.
- RED (raw): `two-line: the caption holds 1 text piece(s) for 2 line(s) -- the text would be drawn twice` and `the three-line caption holds 1 pieces, not 3` (5 of the 27 caption tests failed). GREEN: **27 passed**.
- The new test (`tests/test_caption.py`) checks, at 1280x720 and 1920x1080 for a one-line, a two-line and a 160+-character caption: one text piece per line, no two pieces overlapping (inflate 0.02u), the caption inside the safe-area width, and `caption_band_top()` still equal to the caption's real top.
- Verified: `python scripts/ci_tests.py` -> **1005 passed, 4 failed, 0 skipped** (188 s; the 4 are the pre-existing Windows environment failures: `test_bootstrap_script.py` x3, `test_tex_path.py` x1). `python scripts/ci_render_gate.py` -> exit 0, `CLEAN: 19 storyboard(s) rendered within the allowlist` (the allowlist stays empty; the only advisory is the pre-existing `compare: text scaled to 25 px`).
- **Lint warnings for the #31 storyboard: 0.**
- New issue filed: [#33](https://github.com/Abu103/animatica-manim/issues/33) -- `bounce_sequence` puts its scale note at a fixed y, so a taller caption runs into it (the same family as #29 and #30: the components do not reserve room for the caption).
- NOT verified: the mechanism inside Manim is still unknown; the leading is a workaround for the measured trigger, not a proof; the caption's look changed (looser leading, 0.3 units taller).

## Status (2026-11-11, Hermes session, card T14 "the graph's legend and its tick labels")
- Branch: `hermes/t14-graph-legend-ticks` (from `main` = `0ac045a`). Merged as PR #26 (`88652e2`).
- Changed: `src/animatica/components/graph.py`, `src/animatica/components/_draw.py`, `tests/test_graph.py` (new), `tests/geometry.py`, `tests/test_caption.py`, `tests/conformance/graph_taylor.json` (new), `tests/conformance/expected.json`, `docs/COMPONENTS.md`.
- **The missing legend**: the legend was only built when the model had labelled *both* curves (`if p.approx_fn.strip() and (p.label or p.approx_label)`). A graph that compared two functions without labels showed two coloured curves and nothing to tell them apart -- the storyboard's third beat has no labels, and the before frame has no legend at all.
- **The legend on the curve**: when there was a legend it was anchored to the axes' top-right corner without looking at the curves or at its own width. On a rising curve (e^x) that corner is exactly where the curve goes: the before frame has the cyan line running through the "2nd-order Taylor" entry. The legend now sits **above** the plot, so no curve can reach it.
- **The tick labels under the caption**: the graph reserved a fixed 3.0 units for the caption instead of measuring it, so the x-axis numbers ended up under a caption that wrapped onto three lines. The plot is now sized against the caption the renderer burns in (`scene.caption_mobject` + `caption_band_top`), and the axis numbers keep a 0.16 u clearance above the caption's top.
- **The video longer than the beat**: Manim rounds every animation up to a whole frame, and the graph gave every one of a curve's segments the same slice of time; the rounding added up (a clipped curve made the beat 4.8 s long for a declared 4.0 s). The graph now budgets in whole frames (`Clock.frames()` / `Clock.seconds()`), and a curve with more pieces than frames is drawn in groups.
- The legend names a curve from its label when there is one and from its expression when there is not, typeset as LaTeX (`1 + x + x**2/2` -> `1 + x + x^{2}/2`), so the viewer reads math and not Python source. A single-curve graph keeps its label as a title.
- RED proof (raw output in `out/t14_red.txt`): 25 of 51 tests failed -- "the graph drew two curves but no legend", "the axis number at x=-4.44 has its bottom at y=-2.181, under the caption's top y=-2.051", "a three-line caption must push the axis numbers up: -2.181 -> -2.181", "graph: text overlaps -- '' at x[-0.17,-0.07] y[0.86,1.02] vs 'averylonglegendlabelthatstretchesacrossthewholeplot'", "at 15 fps the video is 4.800s long (72 frames) but the beat declares 4.0s (60 frames allowed)".
- Frames: `frames/t14/t14_before_b{0,1,2}_{0.5,mid,hold}.png` and `frames/t14/t14_after_b{0,1,2}_{0.5,mid,hold}.png` (the `frames*/` tree is gitignored, so they are local evidence only).
- Verified: `python scripts/ci_tests.py` -> **999 passed, 4 failed, 0 skipped, 0 errors, 0 warnings** (the 4 are the pre-existing Windows environment failures: `test_bootstrap_script.py` x3, `test_tex_path.py` x1 -- they fail on a clean checkout too). `python scripts/ci_render_gate.py` -> exit 0, `CLEAN: 19 storyboard(s) rendered within the allowlist` (the new `graph_taylor.json` is in the corpus; the allowlist stays empty). `python -m pytest tests/test_graph.py` -> **51 passed**.
- NOT verified: nothing is pushed and no CI has run on this branch; the frames were judged by eye on this Windows box only.

## Status (2026-11-11, Hermes session, card T15 + T16 "the eval baseline")
- Branch: `hermes/m2-eval-baseline`, off `main` = `88652e2` (T14, PR #26, merged by the owner). This branch merged as PR #34 (`e43d00f`).
- Changed: `tests/reference_prompts.txt`, `tests/test_reference_prompts.py`, `docs/EVAL_BASELINE.md` (new), `docs/gallery/eval_*` (new: 5 storyboards + 5 stills), `README.md`, `docs/SESSION_TASKS.md`. **No source changes** (the card allows only the prompt file and the coverage test).
- **T15**: the corpus had 30 prompts for 21 components: ten components (`array_viz`, `bounce_sequence`, `flow`, `formula_derivation`, `matrix`, `number_line`, `parametric_graph`, `recursion_tree`, `stat_callout`, `table`) had no prompt at all, several prompts were near-duplicates, and one prompt carried code (`def f(x): return x * x` was in the *eval* file). The file now has exactly one prompt per component -- 21 lines, no code, including `explain taylor series` and the Fibonacci bounce -- and the coverage test resolves every prompt to exactly one component (by the component's name or by an obvious intent) and requires that resolution to be a bijection onto the registry.
- The offline `TemplateMatcher` check that used to guard this file was **replaced** by the coverage test: the matcher knows ten templates and the registry has twenty-one components, so it cannot express the corpus any more. The matcher's own coverage lives in `tests/test_template.py` and is untouched.
- **T16**: `animatica eval --models nim,groq --prompts tests/reference_prompts.txt --max-retries 2` **could not be run as written**: the eval CLI has no `--model` flag (one `ANIMATICA_MODEL` for the whole process, so two providers cannot have two model ids) and the configured defaults of the second provider are retired (`groq`: HTTP 404 `llama-3.1-8b-instant does not exist`; `openrouter`: HTTP 404 `This model is unavailable for free`). The baseline therefore ran the same harness with the model ids spelled out (`out/t16_eval.py`).
- Baseline (2026-11-11 12:57-13:02, commit `1d6fbc6`, provider `nim`, model `nvidia/nemotron-3.5-super-vl-120b-a12b`): **17/21 first-try valid, 3 retry-valid, 20/21 eventual valid, 1 errored** (`timeline of the history of computers`; the same prompt succeeded minutes later, so it is the model's output, not a broken component). Zero lint warnings on every storyboard that was produced. The full table is in `docs/EVAL_BASELINE.md`.
- groq was dropped at the owner's instruction: with a model the key can reach (`openai/gpt-oss-20b`) the free tier answered 11 of 21 prompts with 19 HTTP 429s in between. The partial result is recorded in the baseline, not rounded into a column.
- **The prompts found five component bugs**, filed as issues with the storyboard that shows them: #28 `array_viz` runs 2.3 s longer than it declares; #29 `formula_derivation` draws its last step under the caption; #30 `steps_list` puts long items outside the safe-area margin; #31 a caption too wide for the frame is **printed twice, overlapping** (found by rendering the Fibonacci bounce; a short caption and a short two-line caption both render clean, so the trigger is `make_caption`'s `scale_to_fit_width`); #32 `parametric_graph` prints its axis numbers with full float precision (`0.7999900318453959`).
- Gallery: `eval_taylor_series`, `eval_recursion_tree`, `eval_bar_chart`, `eval_number_line`, `eval_code_highlight` -- storyboard + MP4 + one still each. The MP4s are not committed (`*.mp4` is ignored); the stills and the storyboards are. Two storyboards the eval scored `ok` are **not** in the gallery because their renders are visibly broken (the Fibonacci bounce and the parametric circle, issues #31 and #32).
- Verified: `python -m pytest tests/test_reference_prompts.py tests/test_eval.py tests/test_ai_prompt.py tests/test_template.py` -> **71 passed**. `python scripts/ci_tests.py` -> see the run below.
- NOT verified: the second provider is not in the baseline (rate limited); the percentages are one run of one model at one temperature; nothing is pushed and no CI has run on this branch.
- OPEN ITEM (not mine, left in the working tree): `scripts/ci_tests.py`, `scripts/ci_render_gate.py`, `src/animatica/backends/scheduler.py` and `tests/test_scheduler.py` carry the owner's in-progress worker-count rework. Not committed here.

## Status (2026-11-11, Hermes session, the LaTeX bundles were rebuilt and republished)
- Branches: `ci/fix-tex-packages` -> **PR #22 (merged, `a8e7146`)**, `ci/tex-bundle-varwidth` -> **PR #23 (merged, `6728df2`)**, `ci/seed-windows-bundle` -> **PR #24 (merged, `2772040`)**.
- Why it was needed: the B4f fix made the installer repair an incomplete bundle, but the *published* bundles still lacked `varwidth.sty`. They are what users download on the first `curl | sh`, so they had to be rebuilt.
- **Linux** `animatica-tex.tar.xz` is built by `tex-deps.yml`, not by `build-tinytex.yml` -- the package list in that file had no `varwidth` (that was the gap PR #22 left). One line; the workflow triggers on its own file, so the PR's run rebuilt the bundle, committed it to the `artifacts` branch and `--clobber`ed the `native-deps-v1` release asset. Verified by downloading it: `./texmf-dist/tex/latex/varwidth/varwidth.sty`, 45 MB, updated 2026-11-10T16:32Z. The `artifacts` branch copy has it too.
- **Windows** `tinytex-manim-win.zip` cannot be refreshed in place: the workflow refuses to replace a published asset, deliberately, because the bundle is not reproducible (it bakes whatever TinyTeX upstream serves that day) and the design is *tag + sha256 as one pair*. So a new release `tex-deps-v2-windows` was published; its `release (published)` event built, verified and uploaded `tinytex-manim-win.zip` (`sha256:0160245663bae6c032538c19536e777c2d49dc5196a7975fbd2e793e9897993c`), its `.sha256`, and the Linux fallback `tinytex-manim.zip` -- all three carry `varwidth.sty`. `src/animatica/tex_bundle.py` is pinned to that pair, and the pinned URL serves exactly the pinned hash (downloaded and compared).
- `gh release edit native-deps-v1 --latest`: a new release makes *itself* the "latest", which would have moved the Linux installer's first URL (`releases/latest/download/...`) to the Windows release. Put back.
- Also: `session-*.json` is in `.gitignore` -- `opencode session export` writes a multi-megabyte transcript into the working directory.
- Handoff for a cold start: `docs/handoffs/2026-11-11-b4-state.md` (the whole B4 effort, its two hidden bugs, the numbers, how to work here).
- NOT verified: a real first-install on a clean Windows box using the new bundle (only the hash and the zip contents were checked).

## Status (2026-11-10, Hermes session, card B4f "the LaTeX packages are complete")
- Branch: `ci/fix-tex-packages` (from `main` = `1bc7ded`). **PR #21 (the apt cache) is still open.**
- Changed: `src/animatica/doctor.py`, `scripts/bootstrap.sh`, `.github/workflows/build-tinytex.yml`, `.github/workflows/build-tinytex-windows.yml`, `tests/test_doctor_fix.py`.
- The bug: neither TinyTeX bundle (`animatica-tex.tar.xz` for Linux, `tinytex-manim.zip` for Windows) carries `varwidth.sty`, and `standalone.cls` loads it for its border box. Every formula therefore failed to compile and the equations degraded to plain text -- while `animatica doctor` reported LaTeX as fine, because the package check only compiles a formula with `--deep`.
- The fix: `varwidth` goes into `TEX_PACKAGES` and `NEEDED_TEX_FILES`, so `doctor --fix` installs it. On Linux the doctor leaves the packages to apt -- but the one-line installer unpacks a TinyTeX bundle, which only tlmgr can complete, so the doctor now recognises that tree and uses tlmgr for it (the system's TeX Live is still left to apt). The installer completes the bundle after unpacking it, with the doctor's own package list. The two bundle workflows install `varwidth` too, so the next bundle is complete.
- Tests: `test_varwidth_is_in_the_package_lists`, `test_a_tex_bundle_on_linux_is_repaired_with_tlmgr`, `test_the_system_texlive_on_linux_is_left_to_apt`.
- NOT fixed (needs the owner): the published `native-deps-v1` and `tex-deps-v1-windows` bundles still lack `varwidth.sty` -- they have to be rebuilt and re-uploaded. Until then the installer completes the bundle itself, which is why the fix works without a new release.
- Found while doing it: the Windows bundle workflow's verification step looked for the bundle in `<root>/.tex/bin/windows`, but since T12b the installer prefers the per-user data dir (`%LOCALAPPDATA%/Animatica/tex`) and only falls back to `<root>/.tex`. The check had been stale since then -- it only runs when that workflow file changes, so nothing had noticed. It now uses the product's own `bundle_bin_dirs()` helper.
- Also: the conformance corpus's `title_card.json` caption described production mechanics, and the guidance lint said so in every gate run. It teaches something now ("Every explainer names its topic up front."), and the gate has **no advisories left**: every storyboard renders with "OK: rendered with no warnings".

## Status (2026-11-10, Hermes session, card B4e "the recursion tree's video was longer than its beat")
- Branch: `hermes/b4-conformance-clean` -> **merged into `main` as `9f12ac9` (PR #19)**. The whole B4 effort (B4, B4b, B4c, B4d, B4e) is now on main.
- Changed: `src/animatica/components/_draw.py`, `src/animatica/components/recursion_tree.py`, `src/animatica/components/array_viz.py`, `src/animatica/frame_lint.py`, `src/animatica/pipeline.py`, `tests/test_recursion_tree.py`, `tests/test_array_viz.py`, `tests/test_frame_lint.py`.
- **The cause of the missing edges**: not skipped edges, not an off-by-one, not a cut budget. Manim writes `ceil(run_time * fps)` frames per animation, so a run time that is not a whole number of frames makes the video longer than the beat. The tree has 29 animations (15 nodes + 14 edges) and the rounding added up: the video was **87 frames = 5.8s for a beat that declares 5.2s**, and the drawing only ended at video t=5.400 -- after the declared end. At 5.1s the last two edges were still fading in, which is why the frame showed 12 of 14.
- The fix at the root: the `Clock` knows the frame rate and can count in frames (`frames()`, `seconds()`, `whole()`), and the tree budgets in them: the title, the nodes and the edges take whole frames and what is left of the budget holds the finished tree. The video is now **77 frames = 5.13s** for the declared 5.2s (one frame short; the drift test allows one).
- The tree is also drawn **from the root down** now: level by level, every child with the edge that leads to it. It used to be drawn from the leaves up, because the layout hands the positions out in the order it placed them and a parent is placed after its children -- the root dropped in last.
- Frames: `b4e_recursion_tree_0.5.png`, `_2.6.png`, `_4.7.png` (the hold before the fade-out). **Edges visible in the hold frame: 14 of 14** (before: 13 of 14 at the same moment, and 12 of 14 at the declared end).
- array_viz: the title is pinned to the top edge (`buff=0.6`) and centred, with the value boxes centred in the space below it (still 70% of the frame width). `test_array_viz_title_keeps_its_place` is replaced by `test_array_viz_title_is_centred_above_the_boxes`. Frame: `b4e_array_viz.png`.
- frame_lint: the caption strip is no longer the constant 0.165. It is derived from the caption band (`caption_band_top()`), measured by the pipeline with the caption the renderer burns in, so a three-line caption is left out completely. RED proof: with the old constant, a beat that shows nothing but a three-line caption was not reported at all.
- RED proofs: `at 15 fps the video is 5.800s long but the beat declares 5.2s` (and 5.767s at 30 fps, 5.517s at 60 fps); the title's top was at y=0.700 instead of y=3.400; the three-line caption test failed with `[]` (no warning).
- Verified: `python scripts/ci_tests.py` -> **944 passed, 4 failed, 0 skipped, 0 errors, 0 warnings** (155.74 s; the 4 are the pre-existing environment failures). `python scripts/ci_render_gate.py` -> exit 0, `CLEAN: 18 storyboard(s) rendered within the allowlist` (72.2 s).
- CI: the first run of this branch was red on Linux, and the log named the cause: the TinyTeX step wrote a bare path into `$GITHUB_ENV`, which takes `NAME=VALUE` pairs (`Invalid format '/home/runner/.../.tex/bin/x86_64-linux'`). The bundle itself worked: downloaded, `varwidth` installed and the probe document compiled in about **seven seconds**, against the **10m47s** the apt step used to take. Fixed in `32b9457` (`echo "PATH=$BIN:$PATH" >> "$GITHUB_ENV"`).
- CI after the fix (run 42834986187): **linux, windows and hyperframes all green**, the Linux job **203 s** against main's 416 s. Step by step: the TeX setup 6 s (the bundle came from `actions/cache`; ~20 s cold) against ~1m55s of apt; the suite **1m25s** against 4m01s (four workers); the render gate **31 s** against ~2m24s (the corpus in parallel).

## Status (2026-11-10, Hermes session, card B4d "recursion_tree edges connect the wrong nodes")
- Branch: `hermes/b4-conformance-clean` (B4 + B4b + B4c + B4d). Merged as PR #19 (`9f12ac9`).
- Changed: `src/animatica/components/recursion_tree.py`, `tests/geometry.py`, `tests/test_recursion_tree.py`.
- Step 0 (the "before" evidence): rendered `tests/conformance/recursion_tree.json` on **origin/main** (`0c0b444`, before B4) and saved the frames `b4d_recursion_tree_main_4.6.png`, `_5.png`, `_5.1.png`. **The edges were already wrong there**: 24 edges drawn for the 14 relations of fib(5), 10 of them to a node that is not the child.
- Root cause: `tree_layout()` computed the real parent -> child relation and threw it away, so `play()` guessed the children from the depth row and the child's argument value -- every node was connected to every matching node in the next row. The guess came in with the component in **cb6dbd4** (2026-11-09, the PR #10 squash that added the file); the B4 budget and fit commits (`92bf01e`, `cb71a54`) never touched it. The edge set is identical on origin/main and on the branch before the fix.
- Fix: `tree_layout()` now returns `({node_id: (call, x, y)}, [(parent_id, child_id), ...])` and the component draws those. 14 edges for the 14 relations, none to a foreign node.
- The reusable check is `assert_edges_connect_parent_and_child()` in `tests/geometry.py`: every edge starts on a node and ends on a node, the two are a parent and a child, no edge touches a third node, and every relation is drawn exactly once.
- RED: `an edge connects 'fib(3)' at x[-4.02,-3.05] to 'fib(1)' at x[-1.27,-0.30], and that is not a parent and its child` (1280x720 and 1920x1080).
- Frames after the fix: `b4d_recursion_tree_0.5.png`, `_2.9.png`, `_5.1.png`.
- Verified: `python scripts/ci_tests.py` -> **937 passed, 4 failed, 0 skipped, 0 errors, 0 warnings** (143.56 s; the 4 are the pre-existing environment failures). `python scripts/ci_render_gate.py` -> exit 0, `CLEAN: 18 storyboard(s) rendered within the allowlist` (71.4 s; the recursion_tree render was re-done because the source fingerprint changed, which is the cache doing its job).
- OPEN ITEM (found, not fixed): the nodes are still drawn leaves-first, because the layout hands them out in the order it placed them (a parent is placed after its children) while the node ids run from the root down. The tree therefore fills in bottom-up and the root drops in last. Cosmetic, not a bug; it was the same before this card.

## Status (2026-11-10, Hermes session, card B4c "make the tests fast")
- Branch: `hermes/b4-conformance-clean` (B4 + B4b + B4c), 19 commits on `main` (`0c0b444`). Merged as PR #19 (`9f12ac9`).
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
- [x] 3. Feature plan written: docs/ROADMAP.md (spec, was DRAFT; see its header) + docs/TASKS_FOR_HERMES.md (9 task cards)
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

## Status (2026-11-14, Claude session, card T26d "--narrate / --voice, hold + mux")
- `make --narrate [--voice]`: lazy-fetch Piper + voice, synthesize each beat's caption, clip length = beat floor (`RenderOptions.beat_floors`), `Clock` holds content before the fade-out, one track built on final beat timing, muxed to `video_narrated.mp4`; captions/lint use extended durations; `report.json` records voice + license.
- Also fixed T26c: the `narration` doctor check is now an optional tip (ok=True), since a FAIL broke `animatica doctor` in CI and `sandbox.sh`.
- Verified: tests/test_narrate_make.py (13), full suite 1336 passed / 12 failed -- the same 12 fail on the T26c baseline (graph/caption-room/scheduler, sandbox-specific). Real Manim render with fake 5s clips gave a 5.0s video with audio.
- Unverified: real Piper synthesis; voice-model sha256; Windows (Piper asset is Linux-only, fails closed). Card exceeds the 5-file/150-line guideline (rule 10), flagged.
