# Animatica Studio UX Implementation Plan

> **For agentic workers:** Implement this plan task-by-task with test-first
> development. Keep changes on `arena/b5effee8-animatica-manim`; do not merge to
> `main` without explicit approval.

**Goal:** Turn the current tab-heavy Textual studio into a minimal, prompt-first
four-step wizard that is comfortable for first-time users.

**Architecture:** Keep `AnimaticaTuiApp` and the existing render pipeline. Replace
user-facing tabs with a `ContentSwitcher` and explicit progress/navigation,
progressively disclose alternate sources and advanced settings, and preserve the
existing progress/status workers. Use Textual's `run_test()` pilot for interaction
and 80×24 layout checks.

**Tech Stack:** Python, Textual, pytest, pytest-asyncio.

**Spec:** `docs/superpowers/specs/2026-11-07-animatica-studio-ux.md`

## Global Constraints

- The smallest supported terminal is 80×24.
- Keyboard and mouse both work; shortcuts are optional accelerators only.
- Keep Windows/PowerShell support and the real-work progress model.
- Preserve the four stages and all existing render/output behavior.
- No source-code copy from reference projects; no web UI or runtime skill CLI.

## Review Focus

- Empty prompt or an unselected alternate input must produce a clear action, not
  an exception or dead end.
- Switching input modes must not leave two sources active.
- Missing, malformed, or invalid storyboards must stay on the review step with a
  useful message.
- An 80×24 screen must expose the current action and all essential controls.
- Output overwrite warnings, render failures, cancellation, and indeterminate
  progress must remain honest and recoverable.

## Execution Status — 2026-11-07

- Tasks 1–4 implemented: one-step `ContentSwitcher` wizard, visible Back and
  Continue controls, explicit source modes, readable scene preview, collapsed
  JSON and job options, responsive header, and in-app help.
- TUI regression suite: **37 passed** with warnings treated as errors.
- Full local gate: **734 passed, 0 failed, 0 skipped, 0 errors, 0 warnings**.
- Windows CI validation and publishing remain pending; no commit or push was
  performed.

---

### Task 1: Pin down the new first-run and navigation behavior

**Files:** `tests/test_tui.py`

1. Add pilot tests for one-stage-at-a-time navigation, visible Back/Continue
   buttons, current-step text, help access, and 80×24 layout.
2. Add tests that the default prompt mode hides alternate source controls and
   that switching to template/file mode reveals only that mode.
3. Run the new tests and confirm they fail for the current tabbed UI.

### Task 2: Replace tab navigation with a simple wizard shell

**Files:** `src/animatica/tui.py`, `tests/test_tui.py`

1. Add failing tests for prompt → storyboard → style → render and Back behavior.
2. Replace the visible `TabbedContent` strip with a `ContentSwitcher`, compact
   step indicator, and persistent visible Back/Continue actions.
3. Ensure future steps cannot be entered by clicking an unlabeled tab; preserve
   keyboard shortcuts as optional accelerators.
4. Run all TUI pilot tests at 80×24.

### Task 3: Make the normal path minimal and forgiving

**Files:** `src/animatica/tui.py`, `tests/test_tui.py`

1. Add failing tests for prompt-first input modes and collapsed advanced JSON / job
   settings.
2. Implement explicit prompt/template/file modes so source conflicts are
   impossible by construction.
3. Present scene information as a readable preview; put raw JSON behind an
   Advanced disclosure.
4. Keep recommended output/style defaults visible and save the existing
   preferences; put provider/lint/caption knobs behind More options.
5. Run relevant TUI tests, including storyboard validation and saved preferences.

### Task 4: Apply a restrained modern visual system and discoverable help

**Files:** `src/animatica/tui.py`, `tests/test_tui.py`, `docs/TUI.md`

1. Add failing assertions for focus visibility, help, and compact responsive
   header/footer content.
2. Refine Textual CSS with neutral surfaces, one accent, clear primary/secondary
   actions, and no decorative clutter. Keep it readable in Windows Terminal.
3. Add an in-app help screen that explains the workflow and optional shortcuts.
4. Verify layout at 80×24 and a wider size.

### Task 5: Verify the full studio regression set

**Files:** `tests/test_tui.py`, `docs/TUI.md`

1. Run all TUI tests and fix regressions in behavior, not by weakening tests.
2. Run `scripts/ci_tests.py` with the complete local environment; report any
   skips, errors, warnings, or failures honestly.
3. Run the Windows GitHub Actions job after the user approves publishing the
   feature changes; do not merge the PR or touch `main` without approval.
