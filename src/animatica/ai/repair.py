"""Provider-based storyboard generation with a repair loop."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from animatica.ai.base import AIProvider, StoryboardGenerationError, extract_json
from animatica.ai.debug_dump import dump_parse_failure
from animatica.ai.prompt import build_fill_prompt, build_outline_prompt, build_prompt
from animatica.components.registry import ComponentRegistry
from animatica.storyboard.clamp import clamp_lengths
from animatica.storyboard.models import MAX_BEATS, MAX_SCENES, Scene, Storyboard
from animatica.verify.facts import try_facts


def generate_storyboard(
    prompt: str,
    provider: AIProvider,
    registry: ComponentRegistry,
    max_retries: int = 2,
    narrate: bool = False,
    *,
    debug: bool = False,
    out_dir: Path | None = None,
    notes: list[str] | None = None,
) -> Storyboard:
    """Ask `provider` for a storyboard, repairing parse/validation failures.

    Makes one initial call plus up to `max_retries` repair calls. On each failure
    the first 6 errors are appended to the prompt for the next attempt. Raises
    `StoryboardGenerationError` after `max_retries` unsuccessful attempts.
    """
    schema = registry.json_schema()
    current_prompt = build_prompt(prompt, registry, narrate=narrate)
    last_errors: list[str] = []

    for attempt in range(1, max_retries + 2):
        text = provider.generate(current_prompt, schema)
        pending_notes: list[str] = []
        try:
            data = extract_json(text)
            data, clamps = clamp_lengths(data)
            pending_notes.extend(clamps)
            sb = Storyboard.model_validate(data)
        except ValidationError as exc:  # well-formed JSON, wrong shape -> repair
            dump_parse_failure(text, out_dir=out_dir, stage="storyboard", scene=0,
                               attempt=attempt, error=exc, debug=debug)
            last_errors = [
                "parse error: field '{}': {}".format(".".join(str(x) for x in e["loc"]) or "storyboard", e["msg"])
                for e in exc.errors()
            ]
            current_prompt = build_prompt(prompt, registry, last_errors, narrate=narrate)
            continue
        except Exception as exc:  # not JSON at all -> repair
            dump_parse_failure(text, out_dir=out_dir, stage="storyboard", scene=0,
                               attempt=attempt, error=exc, debug=debug)
            last_errors = [f"parse error: {' '.join(str(exc).split())[:200]}"]
            current_prompt = build_prompt(prompt, registry, last_errors, narrate=narrate)
            continue

        errors = registry.validate(sb)
        if not errors:
            if notes is not None:
                notes.extend(pending_notes)
            return sb
        last_errors = errors
        current_prompt = build_prompt(prompt, registry, errors, narrate=narrate)

    raise StoryboardGenerationError(
        f"failed to generate a valid storyboard after retries (provider: {provider.name})",
        last_errors,
    )


# ---- V2b: facts-based verify repair loop -------------------------------


def _finding_error(sb, finding, registry) -> str:
    """One repair error for build_prompt's existing ``errors`` channel.

    Names the beat, the claim sentence and the computed fact texts, so a weak
    model is told *what* was wrong rather than just "a claim failed".
    """
    beat = sb.scenes[finding.beat[0]].beats[finding.beat[1]]
    claim = (beat.narration if finding.field == "narration" else beat.caption) or beat.caption or beat.narration
    facts, _note = try_facts(registry, beat)
    computed = "; ".join(f.text for f in facts) or "no computed facts for this beat"
    return (
        f"scene {finding.beat[0]} beat {finding.beat[1]} {finding.field}: "
        f'"{claim}" ; the code computed: {computed}'
    )


def repair_with_facts(
    prompt: str,
    sb: Storyboard,
    provider: AIProvider,
    registry: ComponentRegistry,
    *,
    narrate: bool = False,
    max_verify_retries: int = 2,
    debug: bool = False,
    out_dir: Path | None = None,
) -> tuple[Storyboard, dict]:
    """Generate -> lint -> verify -> fixes -> send back -> degrade, for models.

    Starts from a schema-valid storyboard already produced by the provider. The
    verify retries here are a budget of their own, separate from the schema
    retries in :func:`generate_storyboard`. Each retry goes through
    ``build_prompt(..., errors=...)``; there is no separate repair template.
    After the budget is spent, surviving error beats have their narration
    blanked (captions are never rewritten) and the run warns.
    """
    from animatica.verify import verify_storyboard  # noqa: PLC0415 - avoid an import cycle
    from animatica.verify.fix import apply_fixes  # noqa: PLC0415

    sb, fix_records = apply_fixes(sb, registry)
    clamps_all: list[str] = []
    sent_back = 0
    errors: list[str] = []
    extra_errors: list[str] = []  # parse failures from a repair call, for the next prompt
    repair_error = ""
    for attempt in range(1, max_verify_retries + 2):
        result = verify_storyboard(sb, registry)
        real_errors = [_finding_error(sb, f, registry) for f in result.findings
                       if f.severity == "error"]
        errors = real_errors + extra_errors
        if not real_errors or sent_back >= max_verify_retries:
            break
        sent_back += 1
        try:
            text = provider.generate(build_prompt(prompt, registry, errors, narrate=narrate), registry.json_schema())
        except Exception as exc:  # a provider failure is not a parse failure: stop here
            sent_back -= 1  # a call that never produced a storyboard was not a send-back
            repair_error = f"repair error from {provider.name}: {type(exc).__name__}: {exc}"
            break
        try:
            candidate_data = extract_json(text)
            candidate_data, clamps = clamp_lengths(candidate_data)
            candidate = Storyboard.model_validate(candidate_data)
        except Exception as exc:  # parse/validation failure: retry with the error text
            dump_parse_failure(text, out_dir=out_dir, stage="repair", scene=0,
                               attempt=attempt, error=exc, debug=debug)
            extra_errors.append(f"parse error: {' '.join(str(exc).split())[:200]}")
            repair_error = f"repair error from {provider.name}: {type(exc).__name__}: {exc}"
            continue
        extra_errors.clear()  # the parse problem is gone; report only real findings now
        repair_error = ""
        if registry.validate(candidate):
            continue
        clamps_all.extend(clamps)
        sb = candidate
        sb, more = apply_fixes(sb, registry)
        fix_records.extend(more)

    # End state: degrade only narration claims that still fail. A caption
    # finding is left as written and stays failed in the report.
    surviving = [
        f for f in verify_storyboard(sb, registry).findings
        if f.severity == "error" and f.field == "narration"
    ]
    degraded: list[list[int]] = []
    if surviving:
        for f in surviving:
            beat = sb.scenes[f.beat[0]].beats[f.beat[1]]
            if beat.narration:
                beat.narration = ""
                degraded.append([f.beat[0], f.beat[1]])
        # A clamp note for narration that has now been blanked describes a
        # change that no longer exists: drop it from the report.
        for si, bi in degraded:
            prefix = f"scene {si} beat {bi} narration:"
            clamps_all = [note for note in clamps_all if not note.startswith(prefix)]

    return sb, {
        "verify": verify_storyboard(sb, registry),
        "fixes": fix_records,
        "sent_back": sent_back,
        "degraded": degraded,
        "errors": errors,
        "repair_error": repair_error,
        "clamps": clamps_all,
    }


# ---- P1.1: two-stage generation (outline -> per-scene fill) ----



class _OutlineBeat(BaseModel):
    component: str
    intent: str = Field(max_length=300)


class _OutlineScene(BaseModel):
    beats: list[_OutlineBeat] = Field(min_length=1, max_length=8)


class _Outline(BaseModel):
    version: str = "1"
    title: str = Field(max_length=300)
    scenes: list[_OutlineScene] = Field(min_length=1, max_length=12)


def _fit_outline(data: Any) -> Any:
    """Keep an outline within MAX_BEATS/MAX_SCENES before validation.

    An oversized scene is split into consecutive scenes of at most 8 beats.
    If that would exceed the scene cap, each original scene is truncated to
    8 beats instead. Neither case burns a provider retry.
    """
    if not isinstance(data, dict) or not isinstance(data.get("scenes"), list):
        return data
    scenes: list[Any] = data["scenes"]
    fits = True

    def beat_list(scene: Any) -> list[Any] | None:
        beats = scene.get("beats") if isinstance(scene, dict) else None
        return beats if isinstance(beats, list) else None

    total = 0
    for scene in scenes:
        beats = beat_list(scene)
        if beats is None or len(beats) <= MAX_BEATS:
            total += 1
        else:
            total += (len(beats) + MAX_BEATS - 1) // MAX_BEATS
    if total > MAX_SCENES:  # splitting would break the scene cap: cap beats
        fits = False

    result: list[Any] = []
    for scene in scenes:
        beats = beat_list(scene)
        if beats is None or len(beats) <= MAX_BEATS:
            result.append(scene if fits else (dict(scene, beats=beats[:MAX_BEATS])
                                              if beats is not None else scene))
            continue
        if not fits:
            result.append(dict(scene, beats=beats[:MAX_BEATS]))
            continue
        result.extend(dict(scene, beats=beats[i:i + MAX_BEATS])
                      for i in range(0, len(beats), MAX_BEATS))
    return dict(data, scenes=result)


def _outline_errors(outline: _Outline, registry: ComponentRegistry) -> list[str]:
    names = registry.names()
    errs = []
    for si, scene in enumerate(outline.scenes, 1):
        for bi, beat in enumerate(scene.beats, 1):
            if beat.component not in names:
                errs.append(f"scene {si}, beat {bi}: unknown component {beat.component!r}. Valid components: {', '.join(names)}")
    return errs


def generate_storyboard_two_stage(
    prompt: str,
    provider: AIProvider,
    registry: ComponentRegistry,
    max_retries: int = 2,
    narrate: bool = False,
    *,
    debug: bool = False,
    out_dir: Path | None = None,
    notes: list[str] | None = None,
) -> Storyboard:
    """Stage 1: outline (component+intent per beat). Stage 2: fill params per scene,
    each fill validated and retried alone. Raises StoryboardGenerationError with the
    collected errors if any stage exhausts its retries."""
    # stage 1: outline
    outline_prompt = build_outline_prompt(prompt, registry)
    last_errors: list[str] = []
    outline: _Outline | None = None
    for attempt in range(1, max_retries + 2):
        text = provider.generate(outline_prompt, registry.json_schema())
        try:
            outline = _Outline.model_validate(_fit_outline(extract_json(text)))
            errs = _outline_errors(outline, registry)
        except ValidationError as exc:
            dump_parse_failure(text, out_dir=out_dir, stage="outline", scene=0,
                               attempt=attempt, error=exc, debug=debug)
            errs = [f"parse error: field '{'.'.join(str(x) for x in e['loc']) or 'outline'}': {e['msg']}" for e in exc.errors()]
        except Exception as exc:
            dump_parse_failure(text, out_dir=out_dir, stage="outline", scene=0,
                               attempt=attempt, error=exc, debug=debug)
            errs = [f"parse error: {' '.join(str(exc).split())[:200]}"]
        if not errs:
            break
        last_errors = errs
        outline_prompt = build_outline_prompt(prompt, registry, errs)
    else:
        raise StoryboardGenerationError(
            f"failed to generate a valid outline after retries (provider: {provider.name})", last_errors
        )
    assert outline is not None

    # stage 2: fill each scene alone
    scenes: list[Scene] = []
    all_errors: list[str] = []
    for si, oscene in enumerate(outline.scenes, 1):
        scene_prompt = build_fill_prompt(prompt, registry, oscene.model_dump(), narrate=narrate)
        scene: Scene | None = None
        for attempt in range(1, max_retries + 2):
            text = provider.generate(scene_prompt, registry.json_schema())
            pending_notes: list[str] = []
            try:
                data = extract_json(text)
                data, clamps = clamp_lengths(data, scene_offset=si - 1)
                pending_notes.extend(clamps)
                sb = Storyboard.model_validate(data)
                errs = registry.validate(sb)
            except ValidationError as exc:
                dump_parse_failure(text, out_dir=out_dir, stage="fill", scene=si,
                                   attempt=attempt, error=exc, debug=debug)
                errs = [f"parse error: field '{'.'.join(str(x) for x in e['loc']) or 'storyboard'}': {e['msg']}" for e in exc.errors()]
            except Exception as exc:
                dump_parse_failure(text, out_dir=out_dir, stage="fill", scene=si,
                                   attempt=attempt, error=exc, debug=debug)
                errs = [f"parse error: {' '.join(str(exc).split())[:200]}"]
            if not errs and len(sb.scenes) == 1:
                scene = sb.scenes[0]
                if notes is not None:
                    notes.extend(pending_notes)
                break
            if not errs:
                errs = [f"fill must return exactly one scene, got {len(sb.scenes)}"]
            last_errors = errs
            scene_prompt = build_fill_prompt(prompt, registry, oscene.model_dump(), errs, narrate=narrate)
        if scene is None:
            all_errors.extend(f"scene {si}: {e}" for e in last_errors)
            continue  # keep the scenes that worked; report the failure
        scenes.append(scene)
    if all_errors:
        raise StoryboardGenerationError(
            f"failed to fill {len(all_errors)} scene(s) after retries (provider: {provider.name})", all_errors
        )
    return Storyboard(version="1", title=outline.title, scenes=scenes)
