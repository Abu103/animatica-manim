# Animatica skill — build explainer-video components as an agent

Use this when asked to add a component, fix a storyboard, or improve an Animatica video.

## The loop (never skip validation)
1. **Read first**: `docs/COMPONENTS.md`, `docs/ROADMAP.md`, `docs/SESSION_TASKS.md`, and the pattern file `src/animatica/components/bounce_sequence.py`.
2. **Scaffold** (if new component): `animatica new-component <snake_name>` — fills module, registry, docs, test, conformance JSON. You only fill the TODOs.
3. **Implement**: `Params` (pydantic, with limits + validators), `duration()` (pure function of params), `play()` (draw/animate; raising degrades to `fallback_text()` + warning, never abort the video), `fallback_text()`.
4. **Validate**: `pytest -q` must pass. Add/extend `tests/test_<name>.py` and `tests/conformance/<name>.json` + `expected.json`.
5. **Render check** (on a machine with manim): `animatica make --from tests/conformance/<name>.json -o /tmp/<name> --quality preview` — must print no Warning.
6. **Log**: append date + result to `docs/SESSION_TASKS.md`.

## Hard rules
- One task card at a time (see `docs/TASKS_FOR_HERMES.md`). Do NOT touch files not listed on the card.
- Never write Manim code at `animatica make` time; model/agent-written component code is dev-time only, reviewed, gated by tests.
- Storyboard JSON v1 is the contract: max 12 scenes, 8 beats/scene, 300 chars per text field. One `bounce_sequence` = one scene, never split.
- Keep `docs/COMPONENTS.md` in sync — a test compares it against the registry.
- If an acceptance command fails twice, stop and write what failed at the bottom of `docs/SESSION_TASKS.md`.

## Commands
- `animatica make "prompt" -o out/ [--provider X --model Y --preview]` — full video
- `animatica make --from storyboard.json -o out/` — re-render without any LLM
- `animatica doctor` / `animatica setup` / `animatica templates` / `animatica guide`
