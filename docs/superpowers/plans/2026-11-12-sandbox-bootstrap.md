# Sandbox Bootstrap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One command takes a bare sandbox (only `curl`, `tar`, `sh`) to a verified working Animatica checkout in under 60 s, on any network tier.

**Architecture:** A live code layer (the repo, wired in by a `.pth`) plus a prebuilt, relocatable runtime layer (standalone Python, wheels, cairo/pango) keyed by a hash of the dependency list. `scripts/sandbox.sh` fetches the runtime through a fallback chain; CI publishes it.

**Tech Stack:** POSIX sh, curl, tar, pytest (file:// fixtures, no network), GitHub Actions, python-build-standalone.

**Spec:** `docs/superpowers/specs/2026-11-12-sandbox-bootstrap-design.md`

## Global Constraints

- Core install budget: under 60 s best and average tier, under 120 s worst tier (`ANIMATICA_BUDGET_S`, default 60).
- Runtime target: Linux x86_64, glibc 2.36 or newer; anything else falls back to `scripts/bootstrap.sh`, unchanged.
- Only `curl`, `tar`, `sh` may be assumed in `scripts/sandbox.sh` and `scripts/runtime_key.sh` (POSIX sh, no bashisms, no zstd, no python before the runtime is unpacked).
- Runtime key: first 12 hex of sha256 over the normalized `dependencies` list of `pyproject.toml`, the Python minor version, and the platform tag.
- Every download is checksum-verified; a mismatch is a failed step.
- Release asset parts on the codeload path stay under 95 MB each.
- `scripts/bootstrap.sh`, `scripts/bootstrap.ps1`, the Windows CI job and all component code are not modified.
- Tests use `file://` URLs through the override variables below; no test touches the network.

## Spec amendments (apply in Task 1, they are plan-level findings)

1. Archive format is `.tar.gz`, not `.tar.zst`: a bare sandbox cannot be assumed to have zstd.
2. The worst tier fetches `refs/heads/runtime-<key>` (one branch per runtime, parts + `SHA256SUMS`), not one shared `artifacts` branch: a codeload branch tarball downloads the whole branch, which would pull every kept runtime. A tiny branch `runtime-latest` holds a `KEY` file naming the newest key. Keep the last 3 `runtime-*` branches.

## Review Focus

1. No `sha256sum` on the host (busybox or macOS style): use `shasum -a 256`, then `openssl dgst`; fail the step if none exist. (Task 2)
2. Re-running the command on an existing root: idempotent, no re-download when the key matches, never overwrites local edits. (Task 3)
3. A download or unpack killed halfway: no half-installed runtime may be used; unpack to a temp dir and rename. (Task 2)
4. A root or home path containing spaces or non-ASCII characters. (Task 3)
5. Wrong platform (aarch64, musl, glibc older than 2.36): clear message and fallback 5, not a crash. (Task 2)

---

## Interfaces (shared names)

Environment overrides, read by `scripts/sandbox.sh`:
`ANIMATICA_GH_REPO` (default `Abu103/animatica-manim`), `ANIMATICA_REF` (default `main`), `ANIMATICA_HOME`, `ANIMATICA_RELEASE_BASE` (default `https://github.com/$REPO/releases/download`), `ANIMATICA_CODELOAD_BASE` (default `https://codeload.github.com/$REPO`), `ANIMATICA_BOOTSTRAP` (default `scripts/bootstrap.sh`), `ANIMATICA_BUDGET_S` (default `60`), `ANIMATICA_PIP_CMD` (tests stub it), `ANIMATICA_TEX_FETCH` (default: built-in TeX fetcher; tests stub it).

Remote layout: release tag `runtime-<key>` with asset `animatica-runtime-<key>.tar.gz` and `SHA256SUMS`; branch `runtime-<key>` with `part-00`, `part-01`, … and `SHA256SUMS` (checksums of the parts and of the joined archive); branch `runtime-latest` with file `KEY`.

Runtime archive root: `python/` (standalone CPython with all dependencies installed), `native/lib/` (cairo, pango and friends).

Functions in `scripts/sandbox.sh` (sourceable when `ANIMATICA_SANDBOX_SOURCE_ONLY=1`):
`runtime_key`, `sha256_of FILE`, `fetch_runtime KEY DEST` (returns 0 on success, prints the source used), `fetch_code ROOT`, `write_env ROOT`, `verify ROOT`, `start_tex ROOT`, `phase NAME` (records elapsed seconds), `main`.

---

### Task 1: Runtime key and spec amendments

**Files:**
- Create: `scripts/runtime_key.sh`
- Test: `tests/test_sandbox_script.py`
- Modify: `docs/superpowers/specs/2026-11-12-sandbox-bootstrap-design.md` (amendments above)

**Interfaces:**
- Produces: `sh scripts/runtime_key.sh [PYPROJECT]` prints the 12-hex key; reads `ANIMATICA_RT_PYTHON` (default `3.12`) and `ANIMATICA_RT_PLATFORM` (default `linux-x86_64`). The CI workflow and `sandbox.sh` both call it, so there is one implementation.

- [ ] **Step 1: Write failing tests** in `tests/test_sandbox_script.py`: `test_key_is_12_hex`, `test_key_is_stable_across_runs`, `test_key_changes_when_a_dependency_changes`, `test_key_ignores_comments_whitespace_and_other_sections`, `test_key_changes_with_python_minor_and_platform`, `test_key_for_the_repo_pyproject_is_computable`.
- [ ] **Step 2: Run** `python -m pytest tests/test_sandbox_script.py -q`. Expected: FAIL (script missing).
- [ ] **Step 3: Implement `scripts/runtime_key.sh`.** Extract lines between `dependencies = [` and the closing `]` of `[project]` with `awk`, drop comments and blanks, sort, hash with whichever of `sha256sum` / `shasum -a 256` / `openssl dgst -sha256` exists.
- [ ] **Step 4: Apply the two spec amendments** and keep the spec's section 5 and 6 consistent.
- [ ] **Step 5: Run** the tests. Expected: PASS.
- [ ] **Step 6: Commit** `scripts: add the runtime key for the sandbox bootstrap`.

### Task 2: Runtime fetch with fallback chain

**Files:**
- Create: `scripts/sandbox.sh` (functions `sha256_of`, `fetch_runtime`, platform check, `main` stub)
- Modify: `tests/test_sandbox_script.py`

**Interfaces:**
- Consumes: `runtime_key.sh` (Task 1).
- Produces: `fetch_runtime KEY DEST`: tries in order (1) release asset, (2) `runtime-KEY` branch parts via codeload, (3) newest runtime from `runtime-latest`, then `$ANIMATICA_PIP_CMD` (default: the runtime's `python -m pip install` of the checkout's `pyproject.toml` dependencies) when PyPI answers, and a printed `WARN` line naming the key mismatch if it does not, (4) returns 1 so `main` runs `$ANIMATICA_BOOTSTRAP`. Unpacks into `DEST.tmp` and renames to `DEST` only when complete. Exit with a platform message and fallback when not Linux x86_64 glibc >= 2.36 (override for tests: `ANIMATICA_RT_FORCE_PLATFORM_OK=1`).

- [ ] **Step 1: Write failing tests** with a `file://` fixture builder (a tiny runtime tarball, parts, checksums): `test_release_asset_is_used_first`, `test_falls_back_to_branch_parts_when_release_missing`, `test_parts_are_joined_and_checksummed`, `test_bad_checksum_is_rejected_and_next_step_tried`, `test_unpublished_key_uses_latest_with_a_warning`, `test_unpublished_key_repairs_with_pip_when_pypi_reachable` (stub pip command), `test_all_sources_failing_runs_bootstrap`, `test_partial_download_never_leaves_a_runtime_dir`, `test_wrong_platform_falls_back_cleanly`, `test_works_without_sha256sum_using_shasum_or_openssl`.
- [ ] **Step 2: Run.** Expected: FAIL (functions missing).
- [ ] **Step 3: Implement** the functions above in POSIX sh; each network step uses `curl -fsSL --max-time` with its own timeout.
- [ ] **Step 4: Run.** Expected: PASS.
- [ ] **Step 5: Commit** `scripts: fetch the sandbox runtime through release, codeload and bootstrap fallbacks`.

### Task 3: Code layer, activation, idempotence

**Files:**
- Modify: `scripts/sandbox.sh` (`fetch_code`, `write_env`, `main` wiring), `tests/test_sandbox_script.py`

**Interfaces:**
- Consumes: `fetch_runtime` (Task 2).
- Produces: `fetch_code ROOT` (uses `git clone --depth 1` when `git` and github.com work; otherwise keeps the extracted tree, runs `git init`, sets `origin` to `https://github.com/$REPO.git`, makes one local commit). `write_env ROOT` writes `ROOT/.animatica-env` (exports `PATH`, `LD_LIBRARY_PATH`, `ANIMATICA_HOME`), an `animatica` shim in `ROOT/.animatica-runtime/bin/`, and `animatica-src.pth` in the runtime's `site-packages` pointing at `ROOT/src`. Layout of the runtime install: `ROOT/.animatica-runtime/`.

- [ ] **Step 1: Write failing tests:** `test_pth_points_at_src_not_a_copy`, `test_added_module_importable_without_rebuild`, `test_deleted_module_stops_importing`, `test_second_run_does_not_redownload_when_key_matches`, `test_second_run_keeps_local_edits`, `test_root_with_spaces_and_non_ascii`, `test_no_git_access_gets_git_init_and_one_commit`.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement** `fetch_code`, `write_env`, and the `main` sequence (code, key, runtime, env). A matching `ROOT/.animatica-runtime/KEY` file means skip the fetch.
- [ ] **Step 4: Run.** Expected: PASS.
- [ ] **Step 5: Commit** `scripts: wire the code layer and activation for the sandbox bootstrap`.

### Task 4: Verify, timings, TeX in the background

**Files:**
- Modify: `scripts/sandbox.sh` (`verify`, `phase`, `start_tex`, final status, flags), `tests/test_sandbox_script.py`

**Interfaces:**
- Consumes: `main` sequence (Task 3).
- Produces: `verify ROOT` runs `animatica doctor` and one smoke render of `scripts/benchmark_storyboards/text_scene.json` through the runtime's python. `start_tex ROOT` fetches `animatica-tex.tar.xz` (release `native-deps-v1`, then the `artifacts` branch `native/animatica-tex.tar.xz`) into `ROOT/.tex` in a background process, never blocking. Final line is exactly one of `READY <seconds>s`, `DEGRADED <reason>`, `FAILED <reason>`. Flags: `--no-tex`, `--verify-only`, `--runtime-only`, `--ref REF`. Exit code non-zero on `FAILED` or when elapsed core seconds exceed `ANIMATICA_BUDGET_S`.

- [ ] **Step 1: Write failing tests:** `test_final_line_is_ready_with_seconds`, `test_degraded_when_latest_runtime_substituted`, `test_exit_nonzero_over_budget` (budget 0), `test_exit_nonzero_when_doctor_fails`, `test_tex_start_does_not_block` (stub sleeps 5 s, `main` returns in under 2 s), `test_no_tex_flag_skips_it`, `test_verify_only_does_not_download`, `test_per_phase_timings_are_printed`.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement** with `date +%s` based `phase`, background TeX via `sh -c '...' &` with output to `ROOT/.tex.log`.
- [ ] **Step 4: Run.** Expected: PASS.
- [ ] **Step 5: Commit** `scripts: verify, time and report the sandbox bootstrap; fetch TeX in the background`.

### Task 5: Runtime build script and publishing workflow

**Files:**
- Create: `scripts/build_runtime.sh`, `.github/workflows/sandbox-runtime.yml`
- Modify: `tests/test_sandbox_script.py`

**Interfaces:**
- Consumes: `runtime_key.sh` (Task 1); the `animatica-native.tar.gz` release asset from `native-deps.yml`.
- Produces: `sh scripts/build_runtime.sh OUTDIR` writes `animatica-runtime-<key>.tar.gz`, `part-NN`, `SHA256SUMS`. `--pack-only DIR OUTDIR` skips the download and install steps (used by tests). python-build-standalone release tag and its sha256 are variables at the top of the script. Workflow triggers: push on `pyproject.toml` and the workflow, nightly `schedule`, `workflow_dispatch`; skips when release `runtime-<key>` exists; publishes release asset, `runtime-<key>` branch, `runtime-latest` branch; prunes to the last 3 `runtime-*` branches.

- [ ] **Step 1: Write failing tests:** `test_pack_only_produces_parts_under_95mb` (parts size limit lowered by env for the test), `test_sha256sums_cover_parts_and_archive`, `test_packed_output_is_fetchable_by_fetch_runtime` (round trip with Task 2), `test_workflow_triggers_and_prune_step` (parse the YAML: paths, schedule, `workflow_dispatch`, a prune step).
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement** the script (download pinned python, `python -m pip install` the pinned dependencies, unpack native bundle into `native/`, strip `__pycache__` and test directories, pack, split) and the workflow (job in `python:3.12-slim-bookworm`).
- [ ] **Step 4: Run** the tests. Expected: PASS. A full build runs only in CI: mark it unverified until the first workflow run is read.
- [ ] **Step 5: Commit** `ci: build and publish the sandbox runtime`.

### Task 6: PR gate and clean-container timing job

**Files:**
- Modify: `.github/workflows/ci.yml`, `tests/test_ci_gate.py`

**Interfaces:**
- Consumes: `runtime_key.sh`, `sandbox.sh`.
- Produces: job `sandbox-runtime-gate` (fails when the PR's key has neither release `runtime-<key>` nor a branch `runtime-<key>` and the PR does not touch `sandbox-runtime.yml`'s trigger paths) and job `sandbox-fast-path` (runs the one command in `debian:bookworm-slim` with only `curl`, `tar`, `sh` plus `ca-certificates`, prints per-phase times, fails over budget).

- [ ] **Step 1: Write failing tests** in `tests/test_ci_gate.py`: `test_ci_has_the_sandbox_gate_job`, `test_ci_has_the_clean_container_timing_job`, `test_gate_job_uses_runtime_key_sh` (parse the workflow YAML).
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement** the two jobs.
- [ ] **Step 4: Run** `python -m pytest tests/test_ci_gate.py -q`. Expected: PASS.
- [ ] **Step 5: Commit** `ci: gate dependency changes on a published runtime and time the fast path`.

### Task 7: Agent entry point and docs

**Files:**
- Modify: `AGENTS.md`, `docs/SETUP.md`, `README.md`, `tests/test_sandbox_script.py`

**Interfaces:**
- Consumes: the command line from `sandbox.sh --help`.
- Produces: the one command and the line `. ./.animatica-env` as the first lines of `AGENTS.md`; a short section in `docs/SETUP.md` listing the flags, tiers and fallback order.

- [ ] **Step 1: Write failing tests:** `test_agents_md_leads_with_the_one_command`, `test_agents_md_command_matches_sandbox_help`, `test_setup_doc_lists_every_flag`.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Update** the three docs.
- [ ] **Step 4: Run the whole suite** (`python scripts/ci_tests.py`, or `pytest -n 4` minus the known environment failures). Expected: no new failures.
- [ ] **Step 5: Commit** `docs: lead AGENTS.md with the one-command sandbox setup`.
