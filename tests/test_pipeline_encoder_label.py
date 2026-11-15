from animatica.pipeline import default_encoder_label


def test_manim_keeps_its_x264_label():
    assert default_encoder_label("manim") == "x264 (manim default)"


def test_other_backends_are_not_labelled_x264():
    # Seen on a real HyperFrames render: "Encoder: x264 (manim default)".
    assert default_encoder_label("hyperframes") == "hyperframes default"
