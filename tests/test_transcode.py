
from animatica.encode.probe import EncoderInfo
from animatica.encode.transcode import transcode


class CP:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_transcode_success_uses_list_args(tmp_path):
    src = tmp_path / "in.mp4"
    src.write_bytes(b"x")
    dst = tmp_path / "out.mp4"
    enc = EncoderInfo("h264_nvenc", "h264_nvenc", True, "")

    captured = {}

    def run(args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        dst.write_bytes(b"out")
        return CP(0, "", "")

    result = transcode(src, dst, enc, ffmpeg="ffmpeg", run=run)
    assert result.path == dst
    assert result.warning is None
    assert result.encoder == enc
    assert isinstance(captured["args"], list)
    assert captured["kwargs"].get("shell") is not True


def test_transcode_failure_keeps_src_and_sets_warning(tmp_path):
    src = tmp_path / "in.mp4"
    src.write_bytes(b"x")
    dst = tmp_path / "out.mp4"
    enc = EncoderInfo("libx264", "libx264", True, "")

    def run(args, **kwargs):
        return CP(1, "", "encode failed")

    result = transcode(src, dst, enc, ffmpeg="ffmpeg", run=run)
    assert result.path == src
    assert src.exists()
    assert result.warning
    assert not dst.exists()

