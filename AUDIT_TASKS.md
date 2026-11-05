# Animatica Audit & Fix Log

Started: 2026-11-04 · Trigger: `animatica make "explain the taylor series"` → `StoryboardGenerationError: failed to generate a valid storyboard after retries`

## Status legend
`[ ]` todo · `[~]` in progress · `[x]` done · `[!]` found, not fixed (needs your input)

## Root-cause investigation
- [x] Read traceback: failure raised at `ai/repair.py:41` after all retries.
- [x] Read every provider (`groq`, `openrouter`, `nim`, `ollama`), `router.py`, `pipeline.py`, `cli.py`, models, registry.
- [x] **ROOT CAUSE 1:** providers get only the raw user prompt (`"explain the taylor series"`). The `schema` argument is accepted by every provider and used by none. The LLM is never told it must emit storyboard JSON, which components exist, or their params. Every attempt (and both repair retries) therefore fails validation.
- [x] **ROOT CAUSE 2 (hides the cause):** `StoryboardGenerationError` is not a `ValueError`, so `cli.make` does not catch it → raw rich traceback, and the validation errors it carries (`.errors`) are never shown. Same for `ProviderError` / `RateLimited`.
- [x] Environment note: sandbox has no `manim`; render tests cannot run here (they pass for you per CURRENT_STATE.md). Generation-path tests do run.

## Findings (all)
| # | Severity | Finding | Status |
|---|----------|---------|--------|
| 1 | Critical | No system instructions / component catalog / schema sent to any LLM | [x] fixed |
| 2 | High | Repair prompt feedback replaces rather than extends instructions; no hint of prior bad output | [x] fixed |
| 3 | High | CLI shows traceback for `StoryboardGenerationError`, `ProviderError`, `RateLimited`; validation errors hidden | [x] fixed |
| 4 | Medium | `--provider template` advertised in help but router raises "unknown provider" | [x] fixed |
| 5 | Medium | No `max_tokens` on cloud calls: provider defaults can truncate long JSON → parse errors | [x] fixed |
| 6 | Low | `StoryboardCache` is instantiated in `pipeline.py` but never read/written | [x] fixed |
| 8 | Medium | Existing `test_make_cli.py` tests patched `animatica.ai.router.get_provider`, but `pipeline` imports the name directly, so the patch never took effect and the provider path was untested | [x] fixed (patch `animatica.pipeline.get_provider`) |
| 9 | Low | Unexpected exceptions in `make` printed a full rich traceback even without `--debug` | [x] fixed |
| 10 | Medium | Command registered as `setup-cmd` but all messages say `animatica setup` (seen in your --help) | [x] fixed (`@app.command("setup")`) |
| 11 | High | Multi-scene render crashed at the ffmpeg concat step (`exit 4294967294` = -2) with relative `-o` dir: list entries are resolved relative to the list file's folder (out-try4/out-try4/...), and Windows backslashes are escapes in concat syntax. Single-scene template runs never hit it | [x] fixed (absolute, forward-slash, quote-escaped paths; ffmpeg stderr now shown). Verified with real ffmpeg + relative dir |
| 7 | High | NIM returned `HTTP 404: 404 page not found` on your machine: default model `mistralai/mixtral-8x7b-instruct` appears retired | [x] default now `meta/llama-3.1-8b-instruct` (listed on build.nvidia.com); added `--model` / `ANIMATICA_MODEL` override; HTTP 400/404/410 errors now name the model and the override. Not verified against live NIM from sandbox |

## Work log
- Set up sandbox, installed deps, baseline: 24 passed in AI-related tests (1 render test needs manim).
- TDD: wrote `tests/test_ai_prompt.py` (13 tests) first; confirmed red (module missing), then green.
- Added `src/animatica/ai/prompt.py`; `repair.py` now builds instruction + catalog + example + request (+ up to 6 per-field errors on retry).
- `cli.py`: friendly output for `StoryboardGenerationError` (lists the validation errors), `ProviderError`, `RateLimited`, and any other exception; `--debug` re-raises.
- `pipeline.py`: `--provider template` message; wired `StoryboardCache` (only created on the AI path, corrupt entries ignored).
- `groq/nim/openrouter`: `max_tokens: 4096`.
- `CHANGELOG.md` updated.

## Verification (sandbox: Python 3.13, no manim)
- Full suite: **162 passed, 17 skipped, 5 failed**. All 5 failures are `ModuleNotFoundError: No module named 'manim'` (4 render-path CLI tests + `test_doctor::test_all_present_ok`): environment-only, they need your Windows venv.
- New + related AI tests: 13/13 new pass; repair/providers/router/template all pass.
- NOT verified: a real LLM call and a real render (no API keys / manim here).

## Please run on your machine
1. `git pull`/copy the changed files, then `pytest -q` (expect all green, ~190 tests).
2. `animatica make "explain the taylor series" -o E:\animatica-v1\out-nim-try3\ --provider nim`
3. If it still fails you will now see the exact validation errors; paste them and I will tune the prompt. Add `--debug` for the traceback.
4. Finding 7: if you get an HTTP 404/410 from NIM, change `default_model` in `ai/nim.py` to a model listed in your NIM account (e.g. a `meta/llama-3.1-*-instruct`).

## Update 2 (after your Windows run)
- Your env: doctor reported only `latex` failing (dvisvgm=no). You installed TinyTeX via choco and ran refreshenv.
- Fixed finding 10 (`setup` command name) + test.
- Next on your side: open a NEW terminal, activate the venv, run `animatica doctor`. If dvisvgm is still missing: `tlmgr install dvisvgm standalone preview` (TinyTeX bin dir must be on PATH: C:\tools\tinytex\bin\windows).

## Update 3 (your doctor passed; make hit NIM 404)
- doctor: all 7 checks OK on your machine (TinyTeX fix confirmed).
- `make --provider nim` now reaches NVIDIA (the prompt fix works) but returns 404. Fixed per finding 7 above.
- Suite: 166 passed, 17 skipped, 5 failed (all `No module named 'manim'`, sandbox only).
- Try: `animatica make "explain the taylor series" -o out-try4 --provider nim` ; if 404 again: `--model <id from build.nvidia.com>`.

## Update 4 (your try4 run)
- AI path confirmed working end to end on your machine: nemotron model returned a valid storyboard and scenes rendered. Only the final join failed -> finding 11, fixed + 2 regression tests + real-ffmpeg check.
- Suite: 168 passed, 17 skipped, 5 failed (sandbox lacks manim only).
- Still unverified: full render on Windows after this fix (please run try5). Possible follow-ups if you see visual issues: per-scene render time (manim is slow on CPU; use `--preview` for 480p15 while iterating).


## Audit 2026-11-05 (review of the Qwen and Hermes+Nemotron work, done on Linux; Windows not run)

### Inputs
- GitHub: `main` and `fix/windows-linux-stability` (tip `1450f8f`, "windows v2"). This is the trusted base: you pushed it and CI ran on it.
- `animatica-manim.rar` (Hermes working tree on branch `fix/windows-setup-nim-model`, HEAD `639d26e`). Branched from `b1c1552`, so it already contained most of the stability work.

### Findings
| # | Severity | Finding | Status |
|---|----------|---------|--------|
| 12 | High | The RAR is damaged: 17 tracked files extract as 0 bytes (`docs/SETUP.md`, `CHANGELOG.md`, `lint.py`, 9 test files, ...), 33 files failed to unpack. Do not run it as is. Git HEAD still holds the real contents | [x] not used; base is the GitHub branch |
| 13 | Medium | Uncommitted `storyboard/models.py` raises limits (`MAX_SCENES` 12->15, `MAX_BEATS` 8->12, `MAX_TEXT` 300->1000). Earlier audit measured test failures with it applied; it also weakens the guard that keeps weak models inside renderable sizes | [!] NOT merged. Decide deliberately; if wanted, change the tests and COMPONENTS.md together |
| 14 | High | Hermes `doctor.py`: always runs tlmgr on Windows/macOS, even when TeX is healthy (slow, network, can break a working install) | [x] replaced by a kpsewhich gate: repair only when a needed file is missing. 3 tests, one red on the old code |
| 15 | Medium | `probe.py`: `wmic` is removed in Windows 11 24H2, so GPU/encoder detection returned nothing there; one missing tool (e.g. `vainfo`) also discarded `nvidia-smi` results | [x] taken from Hermes (CIM fallback, per-tool isolation, injectable `platform`), tests pass |
| 16 | Medium | NIM default model was a small llama; your tests use nemotron | [x] taken from Hermes (`nim.py`, `providers.toml`, test) |
| 17 | Low | `docs/COMPONENTS.md` had `TODO` rows and claimed a test enforced it; no such test existed | [x] taken from Hermes (real params + 2 drift tests) |
| 18 | Medium | README promised "~25-40s" full-quality install; SETUP.md and CI show minutes | [x] README corrected |
| 19 | Low | RAR also carries junk: `wheel/`, `wheelv2/` render output, `__pycache__`, `.pytest_cache`, `.superpowers/` (untracked in git, but inflate the archive) | [x] none of it taken; `.gitignore` already covers most |

### Verification (Linux, Python 3.12, real Manim 0.22.1 + LaTeX + ffmpeg)
- `animatica doctor`: all checks pass.
- Full suite: **345 passed** (baseline of the pushed branch: 330).
- `scripts/ci_smoke.py`: real render OK, with spaces and non-ASCII (`ü`, `é`) in the output path.
- `bash -n scripts/bootstrap.sh`: OK. PowerShell parse not run here (no `pwsh`); CI's Windows job does it.
- NOT verified: anything on Windows (including your college PC result: you said it ran there, but I have no log), live NIM calls, the bootstrap one-liner end to end.

### Next tasks (priority order)
1. [ ] Push `integrate/audit-2026-11-05` and open a PR into `fix/windows-linux-stability`; wait for the Windows + Linux CI result.
2. [ ] On Windows run `python -m animatica doctor`, then `python scripts/ci_smoke.py`; paste output if anything is red.
3. [ ] Decide finding 13 (limits) on purpose, not by accident.
4. [ ] Known quality issues from before: LaTeX shown as raw text in some videos, fibonacci bouncing-ball quality.
5. [ ] Merge to `main` only after both OS jobs are green; then tag a release.
6. [ ] Web UI only after that.
