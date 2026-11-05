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


def _device_calls_for(platform: str) -> int:
    """How many subprocesses THIS platform's device detection issues, measured not guessed.

    Linux probes nvidia-smi and vainfo; Windows used to probe only wmic. Hard-coding either number is
    what made the old cache test fail on the Windows CI runner (`assert 8 == (6 + 3)`) while the product
    behaved identically.
    """
    counter = FakeRun("", "")
    detect_devices(run=counter, platform=platform)
    return len(counter.calls)


@pytest.mark.parametrize("platform", ["linux", "win32", "darwin"])
def test_probe_cache_hit_repeats_only_version_and_device_probe(platform):
    run = FakeRun("ffmpeg version 6.0", " h264_nvenc h264_qsv libx264 ", 0)
    device_calls = _device_calls_for(platform)
    assert device_calls >= 1, f"{platform} device detection issues no calls at all"

    probe_encoders(ffmpeg="ffmpeg", run=run, cache_dir=None, platform=platform)
    first_calls = len(run.calls)
    probe_encoders(ffmpeg="ffmpeg", run=run, cache_dir=None, platform=platform)
    added = run.calls[first_calls:]

    # the second run is a cache hit: -version and the platform's device tools only
    assert len(added) == 1 + device_calls
    assert sum(1 for c in added if c[1:] == ["-version"]) == 1
    # ... and nothing that costs real work is repeated
    assert sum(1 for c in added if c[1:] == ["-encoders"]) == 0
    assert sum(1 for c in added if "testsrc=size=256x256:rate=1:duration=1" in c) == 0
    # across both runs the encoder list was read exactly once, and test encodes happened once
    assert sum(1 for c in run.calls if c[1:] == ["-encoders"]) == 1
    assert sum(1 for c in run.calls if "testsrc=size=256x256:rate=1:duration=1" in c) == 3


def test_probe_cache_hit_returns_the_same_results():
    run = FakeRun("ffmpeg version 6.0", " h264_nvenc h264_qsv libx264 ", 0)
    first = probe_encoders(ffmpeg="ffmpeg", run=run, cache_dir=None)
    second = probe_encoders(ffmpeg="ffmpeg", run=run, cache_dir=None)
    assert first == second and first, "cached probe must return the same verified encoders"


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



# --- detect_devices: per-tool isolation, and Windows after WMIC removal -----------------------------
# wmic.exe is removed from supported Windows 11 (24H2/25H2) and from GitHub's windows-2025 runner
# images, so GPU discovery silently returned [] there. Get-CimInstance is the documented replacement.


def test_windows_without_wmic_falls_back_to_powershell_cim():
    seen = []

    def run(args, **kw):
        seen.append(list(args))
        if args[0] == "wmic":
            raise FileNotFoundError("wmic")
        return CP(0, "NVIDIA GeForce RTX 4060\nIntel(R) UHD Graphics\n")

    devs = detect_devices(run=run, platform="win32")
    assert [d.name for d in devs] == ["NVIDIA GeForce RTX 4060", "Intel(R) UHD Graphics"]
    assert all(d.vendor == "windows" for d in devs)
    assert seen[0][0] == "wmic" and seen[1][0] == "powershell"


def test_windows_falls_back_when_wmic_reports_nothing_but_a_header():
    def run(args, **kw):
        if args[0] == "wmic":
            return CP(0, "Name\n\n")           # present but useless: header only
        return CP(0, "AMD Radeon 780M\n")

    devs = detect_devices(run=run, platform="win32")
    assert [d.name for d in devs] == ["AMD Radeon 780M"]


def test_one_missing_tool_does_not_hide_the_other():
    def run(args, **kw):
        if args[0] == "nvidia-smi":
            raise FileNotFoundError("nvidia-smi")
        if args[0] == "vainfo":
            return CP(0, "vainfo: VA Profile: Intel iHD driver\n")
        return CP(0, "")

    devs = detect_devices(run=run, platform="linux")
    assert [d.vendor for d in devs] == ["vaapi"]


def test_a_failing_tool_is_not_reported_as_a_device():
    def run(args, **kw):
        if args[0] == "nvidia-smi":
            return CP(1, "", "NVIDIA-SMI has failed because it couldn't communicate")
        return CP(0, "")

    assert detect_devices(run=run, platform="linux") == []


def test_detect_devices_still_never_raises_when_every_tool_fails():
    def run(args, **kw):
        raise OSError("no tools anywhere")

    for plat in ("linux", "win32", "darwin"):
        assert detect_devices(run=run, platform=plat) == []
