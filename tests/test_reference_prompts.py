from pathlib import Path

from animatica.ai.template import TemplateMatcher
from animatica.components.registry import default_registry

PROMPTS = [
    line.strip()
    for line in (Path(__file__).parent / "reference_prompts.txt").read_text().splitlines()
    if line.strip()
]


def test_reference_prompts_count():
    assert len(PROMPTS) == 30


def test_reference_prompts_resolve_via_templates_no_provider_calls():
    matcher = TemplateMatcher()
    reg = default_registry()
    for p in PROMPTS:
        sb = matcher.match(p)
        assert sb is not None, f"no template matched: {p}"
        assert reg.validate(sb) == [], f"invalid storyboard for: {p}: {reg.validate(sb)}"

