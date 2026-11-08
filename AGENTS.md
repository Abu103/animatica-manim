# Animatica: rules for any coding agent (Hermes, Claude, others)

Read this first, every session. These rules beat your own habits.

## What this repo is
Prompt or storyboard JSON -> validated components -> deterministic Manim render -> MP4.
Models choose components and fill short JSON. Reviewed Python code does layout and rendering.
NEVER execute or generate Manim code at `animatica make` time. Component code is dev-time only, reviewed, test-gated.

## Where things are
- Agent loop for components/storyboards: `skills/animatica/SKILL.md`
- Task cards: `docs/TASKS_FOR_HERMES.md` (T1-T9, done), `docs/TASKS_FOR_HERMES_V02.md` (current)
- Roadmap (DRAFT until owner approves): `docs/ROADMAP.md`
- Session log: `docs/SESSION_TASKS.md`  | Playbook: `docs/HERMES_PLAYBOOK.md`
- Gate scripts: `scripts/ci_tests.py` (strict), `scripts/ci_smoke.py`, `animatica doctor`

## Non-negotiable rules
1. ONE task card per session. Touch only files the card lists. Need another file? Stop and ask.
2. Evidence before edits. For any failure, get the real error text first (CI: `gh run view <id> --log-failed`). Do not theorize from a test name.
3. Two-strike rule. If two fix attempts fail, STOP. Write a handoff packet (see playbook section 6) and wait. Do not try a third variation.
4. Tests first. Write a test that fails for the right reason, then make it pass. Never weaken, skip, or delete a test to get green unless the card says so.
5. Say "verified" only for commands you ran in this session and whose output you read. Everything else is "unverified". List unverified items explicitly at the end.
6. No push, no merge, no force-push, no touching `main` or other branches without the owner's explicit "yes" in this session.
7. One branch per card, named `hermes/<card-id>-<slug>`, branched from the current integration branch. Small commits, imperative messages.
8. Do not invent APIs, flags, file paths, or URLs. Read the source or run `--help`. Links must be fetched and confirmed live before you include them.
9. Cross-platform: this project must pass on Linux and Windows CI. In TUI tests press widgets (`widget.press()`), do not rely on mouse geometry. Use `pathlib`, never hardcode `/` or `\`.
10. Size limit: a card should change <= 5 files and ~150 lines. If it grows, stop and say so; do not push through.
11. Before using or fixing a third-party API call you are unsure of, follow the external-docs-lookup skill.

## Definition of done (all must be true)
- Card's acceptance command passes (output pasted).
- `python scripts/ci_tests.py` passes, or you state exactly which tests you could not run and why.
- `docs/COMPONENTS.md` in sync if components changed (a test checks it).
- Entry appended to `docs/SESSION_TASKS.md` (date, card, result, unverified items).
- Handoff packet written if the card is a milestone end.

## Style
Plain, direct reports. No hedging filler. Show commands and real output, not summaries of them.
