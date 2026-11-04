import subprocess
from pathlib import Path

import pytest

import animatica.encode.probe as probe_mod

from animatica.encode.probe import (
    DeviceInfo,
    EncoderInfo,
    detect_devices,
    pick_encoder,
    probe_encoders,
)


@pytest.fixture(autouse=True)
def _clear_encoder_cache():
    probe_mod._ENCODER_CACHE.clear()


class CP:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class FakeRun:
    """Records calls; returns canned CompletedProcess-like objects."""

    def __init__(self, version_out="", encoders_out="", test_encode_rc=0):
        self.version_out = version_out
        self.encoders_out = encoders_out
        self.test_encode_rc = test_encode_rc
        self.calls = []

    def __call__(self, args, **kwargs):
        self.calls.append(list(args))
        a = list(args)
        if a[1:] == ["-version"]:
            return CP(0, self.version_out)
        if a[1:] == ["-encoders"]:
            return CP(0, self.encoders_out)
        return CP(self.test_encode_rc, "", "")


def test_probe_order_nvenc_qsv_x264():
    run = FakeRun("ffmpeg version 6.0", " h264_nvenc h264_qsv libx264 ", 0)
    infos = probe_encoders(ffmpeg="ffmpeg", run=run, cache_dir=None)
    assert [i.name for i in infos] == ["h264_nvenc", "h264_qsv", "libx264"]
    assert all(i.verified for i in infos)


def test_probe_nvenc_fails_verified_false_qsv_picked():
    calls = []

    def run(args, **kwargs):
        calls.append(list(args))
        a = list(args)
        if a[1:] == ["-version"]:
            return CP(0, "ffmpeg version 6.0")
        if a[1:] == ["-encoders"]:
            return CP(0, " h264_nvenc h264_qsv libx264 ")
        if "-c:v" in a and "h264_nvenc" in a:
            return CP(1, "", "nvenc failed")
        return CP(0, "", "")

    infos = probe_encoders(ffmpeg="ffmpeg", run=run, cache_dir=None)
    assert infos[0].name == "h264_nvenc"
    assert infos[0].verified is False
    assert infos[0].reason
    assert infos[1].name == "h264_qsv"
    assert infos[1].verified is True
    picked = pick_encoder("auto", infos)
    assert picked.name == "h264_qsv"


def test_probe_no_ffmpeg_returns_x264_only():
    def boom(args, **kwargs):
        raise FileNotFoundError("ffmpeg")

    infos = probe_encoders(ffmpeg="ffmpeg", run=boom, cache_dir=None)
    assert len(infos) == 1
    assert infos[0].name == "libx264"
    assert infos[0].verified is False
    assert "ffmpeg" in infos[0].reason.lower()


def test_probe_cache_skips_second_run():
    run = FakeRun("ffmpeg version 6.0", " h264_nvenc h264_qsv libx264 ", 0)
    probe_encoders(ffmpeg="ffmpeg", run=run, cache_dir=None)
    first_calls = len(run.calls)
    probe_encoders(ffmpeg="ffmpeg", run=run, cache_dir=None)
    # cache hit: only version + device detection re-run (3 calls), no -encoders or test encodes
    assert len(run.calls) == first_calls + 3
    encoders_calls = [c for c in run.calls if c[1:] == ["-encoders"]]
    assert len(encoders_calls) == 1  # -encoders probed only once


def test_pick_encoder_auto_returns_first_verified():
    infos = [
        EncoderInfo("h264_nvenc", "h264_nvenc", False, "busy"),
        EncoderInfo("h264_qsv", "h264_qsv", True, ""),
        EncoderInfo("libx264", "libx264", True, ""),
    ]
    assert pick_encoder("auto", infos).name == "h264_qsv"


def test_pick_encoder_x264_forces_software():
    infos = [
        EncoderInfo("h264_nvenc", "h264_nvenc", True, ""),
        EncoderInfo("libx264", "libx264", True, ""),
    ]
    assert pick_encoder("x264", infos).name == "libx264"


def test_pick_encoder_unknown_raises():
    infos = [EncoderInfo("libx264", "libx264", True, "")]
    with pytest.raises(ValueError) as exc:
        pick_encoder("h264_nvenc", infos)
    assert "libx264" in str(exc.value)


def test_detect_devices_never_raises():
    def boom(*a, **k):
        raise FileNotFoundError("x")

    assert detect_devices(run=boom, platform="linux") == []

