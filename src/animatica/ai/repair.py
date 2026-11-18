"""Provider-based storyboard generation with a repair loop."""
from __future__ import annotations

from pydantic import BaseModel, Field, ValidationError

from animatica.ai.base import AIProvider, StoryboardGenerationError, extract_json
from animatica.ai.prompt import build_fill_prompt, build_outline_prompt, build_prompt
from animatica.components.registry import ComponentRegistry
from animatica.storyboard.models import Scene, Storyboard
from animatica.verify.facts import try_facts


def generate_storyboard(
    prompt: str,
    provider: AIProvider,
    registry: ComponentRegistry,
    max_retries: int = 2,
    narrate: bool = False,
) -> Storyboard:
    """Ask `provider` for a storyboard, repairing parse/validation failures.

    Makes one initial call plus up to `max_retries` repair calls. On each failure
    the first 6 errors are appended to the prompt for the next attempt. Raises
    `StoryboardGenerationError` after `max_retries` unsuccessful attempts.
    """
    schema = registry.json_schema()
    current_prompt = build_prompt(prompt, registry, narrate=narrate)
    last_errors: list[str] = []

    for _ in range(max_retries + 1):
        text = provider.generate(current_prompt, schema)
        try:
            data = extract_json(text)
            sb = Storyboard.model_validate(data)
        except ValidationError as exc:  # well-formed JSON, wrong shape -> repair
            last_errors = [
                "parse error: field '{}': {}".format(".".join(str(x) for x in e["loc"]) or "storyboard", e["msg"])
                for e in exc.errors()
            ]
            current_prompt = build_prompt(prompt, registry, last_errors, narrate=narrate)
            continue
        except Exception as exc:  # not JSON at all -> repair
            last_errors = [f"parse error: {' '.join(str(exc).split())[:200]}"]
            current_prompt = build_prompt(prompt, registry, last_errors, narrate=narrate)
            continue

        errors = registry.validate(sb)
        if not errors:
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
    sent_back = 0
    errors: list[str] = []
    repair_error = ""
    for _ in range(max_verify_retries + 1):
        result = verify_storyboard(sb, registry)
        errors = [_finding_error(sb, f, registry) for f in result.findings if f.severity == "error"]
        if not errors or sent_back >= max_verify_retries:
            break
        sent_back += 1
        try:
            text = provider.generate(build_prompt(prompt, registry, errors, narrate=narrate), registry.json_schema())
            candidate = Storyboard.model_validate(extract_json(text))
        except Exception as exc:  # provider/parse failure stops the retries
            sent_back -= 1  # a call that never produced a storyboard was not a send-back
            repair_error = f"repair error from {provider.name}: {type(exc).__name__}: {exc}"
            break
        if registry.validate(candidate):
            continue
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

    return sb, {
        "verify": verify_storyboard(sb, registry),
        "fixes": fix_records,
        "sent_back": sent_back,
        "degraded": degraded,
        "errors": errors,
        "repair_error": repair_error,
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
) -> Storyboard:
    """Stage 1: outline (component+intent per beat). Stage 2: fill params per scene,
    each fill validated and retried alone. Raises StoryboardGenerationError with the
    collected errors if any stage exhausts its retries."""
    # stage 1: outline
    outline_prompt = build_outline_prompt(prompt, registry)
    last_errors: list[str] = []
    outline: _Outline | None = None
    for _ in range(max_retries + 1):
        text = provider.generate(outline_prompt, registry.json_schema())
        try:
            outline = _Outline.model_validate(extract_json(text))
            errs = _outline_errors(outline, registry)
        except ValidationError as exc:
            errs = [f"parse error: field '{'.'.join(str(x) for x in e['loc']) or 'outline'}': {e['msg']}" for e in exc.errors()]
        except Exception as exc:
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
        for _ in range(max_retries + 1):
            text = provider.generate(scene_prompt, registry.json_schema())
            try:
                data = extract_json(text)
                sb = Storyboard.model_validate(data)
                errs = registry.validate(sb)
            except ValidationError as exc:
                errs = [f"parse error: field '{'.'.join(str(x) for x in e['loc']) or 'storyboard'}': {e['msg']}" for e in exc.errors()]
            except Exception as exc:
                errs = [f"parse error: {' '.join(str(exc).split())[:200]}"]
            if not errs and len(sb.scenes) == 1:
                scene = sb.scenes[0]
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
