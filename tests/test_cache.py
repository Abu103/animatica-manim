
from animatica.storyboard.cache import StoryboardCache
from animatica.storyboard.models import Storyboard

SB = Storyboard.model_validate(
    {
        "version": "1",
        "title": "T",
        "scenes": [
            {
                "beats": [
                    {
                        "component": "title_card",
                        "params": {"title": "H"},
                    }
                ]
            }
        ],
    }
)


def test_cache_key_and_roundtrip(tmp_path):
    c = StoryboardCache(tmp_path)
    k1 = c.key("prompt", "prov", "1")
    k2 = c.key("prompt", "other", "1")
    k3 = c.key("prompt2", "prov", "1")
    assert len({k1, k2, k3}) == 3
    assert c.get(k1) is None
    c.put(k1, SB)
    assert c.get(k1) == SB

