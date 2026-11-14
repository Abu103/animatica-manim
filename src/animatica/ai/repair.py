"""Provider-based storyboard generation with a repair loop."""
from __future__ import annotations

from pydantic import BaseModel, Field, ValidationError

from animatica.ai.base import AIProvider, StoryboardGenerationError, extract_json
from animatica.ai.prompt import build_fill_prompt, build_outline_prompt, build_prompt
from animatica.components.registry import ComponentRegistry
from animatica.storyboard.models import Scene, Storyboard


def generate_storyboard(
    prompt: str,
    provider: AIProvider,
    registry: ComponentRegistry,
    max_retries: int = 2,
) -> Storyboard:
    """Ask `provider` for a storyboard, repairing parse/validation failures.

    Makes one initial call plus up to `max_retries` repair calls. On each failure
    the first 6 errors are appended to the prompt for the next attempt. Raises
    `StoryboardGenerationError` after `max_retries` unsuccessful attempts.
    """
    schema = registry.json_schema()
    current_prompt = build_prompt(prompt, registry)
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
            current_prompt = build_prompt(prompt, registry, last_errors)
            continue
        except Exception as exc:  # not JSON at all -> repair
            last_errors = [f"parse error: {' '.join(str(exc).split())[:200]}"]
            current_prompt = build_prompt(prompt, registry, last_errors)
            continue

        errors = registry.validate(sb)
        if not errors:
            return sb
        last_errors = errors
        current_prompt = build_prompt(prompt, registry, errors)

    raise StoryboardGenerationError(
        f"failed to generate a valid storyboard after retries (provider: {provider.name})",
        last_errors,
    )



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
        scene_prompt = build_fill_prompt(prompt, registry, oscene.model_dump())
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
            scene_prompt = build_fill_prompt(prompt, registry, oscene.model_dump(), errs)
        if scene is None:
            all_errors.extend(f"scene {si}: {e}" for e in last_errors)
            continue  # keep the scenes that worked; report the failure
        scenes.append(scene)
    if all_errors:
        raise StoryboardGenerationError(
            f"failed to fill {len(all_errors)} scene(s) after retries (provider: {provider.name})", all_errors
        )
    return Storyboard(version="1", title=outline.title, scenes=scenes)
