# Animatica skill — build explainer-video components as an agent

Use this when asked to add a component, fix a storyboard, or improve an Animatica video.

## The loop (never skip validation)

### For component development
1. **Read first**: `docs/COMPONENTS.md`, `docs/ROADMAP.md`, `docs/SESSION_TASKS.md`, and the pattern file `src/animatica/components/bounce_sequence.py`.
2. **Scaffold** (if new component): `animatica new-component <snake_name>` — fills module, registry, docs, test, conformance JSON. You only fill the TODOs.
3. **Implement**: `Params` (pydantic, with limits + validators), `duration()` (pure function of params), `play()` (draw/animate; raising degrades to `fallback_text()` + warning, never abort the video), `fallback_text()`.
4. **Validate**: `pytest -q` must pass. Add/extend `tests/test_<name>.py` and `tests/conformance/<name>.json` + `expected.json`.
5. **Render check** (on a machine with manim): `animatica make --from tests/conformance/<name>.json -o /tmp/<name> --quality preview` — must print no Warning.
6. **Log**: append date + result to `docs/SESSION_TASKS.md`.

### For storyboard-driven video creation (agent loop)
1. **Outline**: Ask the model for a scene list (component + intent per beat) via `build_outline_prompt`.
2. **Validate**: `animatica validate storyboard.json` — must return empty errors.
3. **Lint**: `animatica lint storyboard.json` — review notes, fix narrative-order issues.
4. **Render**: `animatica make --from storyboard.json -o out/` — verify video plays.
5. **Preview frame**: `animatica mcp` tool `preview_frame` — inspect a frame at time t to verify visual quality.
6. **Fix**: Edit storyboard.json directly or via `animatica edit out/ "instruction"`, then re-render.

## Hard rules
- One task card at a time (see `docs/TASKS_FOR_HERMES.md`). Do NOT touch files not listed on the card.
- Never write Manim code at `animatica make` time; model/agent-written component code is dev-time only, reviewed, gated by tests.
- Storyboard JSON v1 is the contract: max 12 scenes, 8 beats/scene, 300 chars per text field. One `bounce_sequence` = one scene, never split.
- Keep `docs/COMPONENTS.md` in sync — a test compares it against the registry.
- If an acceptance command fails twice, stop and write what failed at the bottom of `docs/SESSION_TASKS.md`.

## Agent JSON tools (no MCP server needed)
- `animatica list-components` — JSON list of component names
- `animatica component-schema <name>` — JSON params schema
- `animatica validate storyboard.json` — JSON list of errors (empty = valid)
- `animatica lint storyboard.json` — JSON {storyboard, notes} after deterministic lint

## Agent JSON-CLI (MCP mode)
`animatica mcp` reads JSON commands from stdin, writes JSON results to stdout:
- `{"tool":"list_components","args":{}}`
- `{"tool":"component_schema","args":{"name":"<name>"}}`
- `{"tool":"validate_storyboard","args":{"path":"<path>"}}`
- `{"tool":"render_storyboard","args":{"path":"<path>","out_dir":"<dir>","preview":true}}`
- `{"tool":"preview_frame","args":{"video":"<path>","scene_index":0,"t":0.5}}`
- `{"tool":"lint_video","args":{"video":"<path>","scene_durations":[...]}}`

## Commands
- `animatica make "prompt" -o out/ [--provider X --model Y --preview]` — full video
- `animatica make --from storyboard.json -o out/` — re-render without any LLM
- `animatica edit out/ "instruction"` — AI-assisted storyboard edit + re-render
- `animatica doctor` / `animatica setup` / `animatica guide` / `animatica bootstrap` / `animatica eval`
