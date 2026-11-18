# Start prompt for opencode (paste this, then name one card)

You are working in the Animatica repo on branch `dev`. Read, in this order: `AGENTS.md`, `docs/superpowers/specs/2026-11-16-compute-and-verify-design.md`, then `docs/TASKS_FOR_OPENCODE_VERIFY.md` (the card list). Do **only** the card I name, and only the files that card lists.

Rules that matter most: tests first (paste the red run, then the green run); say "verified" only for commands you ran and read; no push, no merge; if a fix fails twice, stop and write a handoff packet; never weaken a test; never invent an API, flag or path, read the source.

Start by running `git status -sb`, `git log --oneline -3`, and `python -m pytest -q -n auto tests -x -q` to record the baseline. Then create the branch `hermes/<card-id>-<slug>` and do the card. End with the report format from the card file, then produce the patch: `git format-patch -1 --stdout > <card-id>.patch`. Wait for review before the next card.
