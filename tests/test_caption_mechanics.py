"""B5: out-2 narrated 'Title card introducing ...' and 'Two columns contrast ...' aloud.

Narration reads the caption (pipeline.beat_text), so a caption that describes the
production instead of teaching is audible. These are the real captions from that render.
"""
import pytest

from animatica.ai.guidance import check_generation_guidance, mechanics_phrase
from animatica.storyboard.lint import lint_storyboard
from animatica.storyboard.models import Storyboard

# every caption below came from the out-2 storyboard.json
OUT2_MECHANICS = [
    "Title card introducing Dijkstra and Bellman-Ford shortest-path algorithms",
    "The walkthrough steps through extracting the minimum node and relaxing its outgoing edges.",
    "Two columns contrast how each algorithm traverses the same graph.",
    "A statistic callout contrasts the two time complexities and notes negative-edge handling.",
    "Define weighted directed graph with positive and negative edges",
    "Present shortest-path relaxation formula d[v] = min(d[v], d[u] + w(u,v))",
    "Show final shortest distances and completed negative-cycle check.",
    "Summarize when to use Dijkstra versus Bellman-Ford",
    "Initialize distance array with source at 0 and others at infinity.",
]
OUT2_TEACHING = [
    "Distance array starts with source at 0 and all others at infinity.",
    "Final shortest-path distances from the source to every node.",
    "Walk through edge relaxations over V-1 passes.",  # imperative-looking but teaches; must stay unflagged
]


def _sb(beats):
    return Storyboard.model_validate(
        {"version": "1", "title": "t", "scenes": [{"beats": [b]} for b in beats]}
    )


@pytest.mark.parametrize("cap", OUT2_MECHANICS)
def test_out2_mechanics_captions_are_detected(cap):
    assert mechanics_phrase(cap) is not None


@pytest.mark.parametrize("cap", OUT2_TEACHING)
def test_out2_teaching_captions_are_not_flagged(cap):
    assert mechanics_phrase(cap) is None


def test_every_out2_mechanics_caption_is_reported_as_a_note():
    sb = _sb([
        {"component": "steps_list", "params": {"items": ["a"]}, "caption": c} for c in OUT2_MECHANICS
    ])
    notes = [n for n in check_generation_guidance(sb) if "production mechanics" in n]
    assert len(notes) == len(OUT2_MECHANICS)


def test_lint_gives_a_flagged_title_card_its_title_as_caption():
    sb = _sb([
        {"component": "title_card", "params": {"title": "Dijkstra vs Bellman-Ford", "subtitle": "Shortest paths"},
         "caption": OUT2_MECHANICS[0]},
    ])
    new, notes = lint_storyboard(sb)
    assert new.scenes[0].beats[0].caption == "Dijkstra vs Bellman-Ford"
    assert any("title_card caption" in n for n in notes)
    # the clean-up removes the warning's cause
    assert not [n for n in check_generation_guidance(new) if "production mechanics" in n]


def test_lint_leaves_good_title_card_caption_and_other_components_alone():
    good = _sb([
        {"component": "title_card", "params": {"title": "T"}, "caption": "Shortest paths on weighted graphs."},
        {"component": "compare", "params": {"title": "x", "left": {"heading": "a", "bullets": ["b"]},
                                            "right": {"heading": "c", "bullets": ["d"]}}, "caption": OUT2_MECHANICS[2]},
    ])
    new, _ = lint_storyboard(good)
    assert [b.caption for s in new.scenes for b in s.beats] == [b.caption for s in good.scenes for b in s.beats]


def test_lint_title_card_rewrite_is_idempotent():
    sb = _sb([{"component": "title_card", "params": {"title": "T"}, "caption": OUT2_MECHANICS[0]}])
    once, _ = lint_storyboard(sb)
    twice, notes = lint_storyboard(once)
    assert twice == once and not any("title_card caption" in n for n in notes)
