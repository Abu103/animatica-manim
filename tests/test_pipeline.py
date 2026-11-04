import pytest

from animatica.pipeline import make_video


@pytest.mark.render
def test_make_end_to_end(tmp_path):
    result = make_video("make a title card about Hello", out_dir=tmp_path, preview=True)
    assert result.video.exists()
    assert result.storyboard.exists()
    assert result.captions.exists()
    assert result.report.exists()
    assert result.warnings == []

