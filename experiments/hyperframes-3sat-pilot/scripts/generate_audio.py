#!/usr/bin/env python3
"""Generate original, subtle UI-like sound accents. No samples, service, or API.
The composition's audio is timed by HyperFrames; this is just its local source asset.
"""
from array import array
from math import cos, exp, pi, sin, tanh
from pathlib import Path
import random
import struct
import wave

RATE = 24000
LENGTH = 28.5
SAMPLES = round(LENGTH * RATE)
buf = array('f', [0.0]) * SAMPLES
rng = random.Random(30917)


def add_chime(at, notes, length=0.85, gain=0.1):
    first = int(at * RATE)
    count = min(int(length * RATE), SAMPLES - first)
    for j in range(count):
        t = j / RATE
        attack = min(1.0, t / 0.022)
        fall = exp(-4.1 * t / length)
        color = sum(sin(2 * pi * f * t) + .21 * sin(2 * pi * f * 2.01 * t)
                    for f in notes) / len(notes)
        buf[first + j] += gain * attack * fall * color


def add_tick(at, high=True):
    first = int(at * RATE)
    for j in range(min(int(.13 * RATE), SAMPLES - first)):
        t = j / RATE
        transient = exp(-36 * t)
        freq = 920 if high else 310
        buf[first + j] += .051 * transient * (sin(2 * pi * freq * t) + .12 * rng.uniform(-1, 1))


# A very quiet, original airy tonal bed. Never drowns out the text.
for i in range(SAMPLES):
    t = i / RATE
    fade = min(1, t / 1.1, (LENGTH - t) / 1.0)
    buf[i] += .0065 * max(fade, 0) * (
        .55 * sin(2 * pi * 110 * t) + .31 * sin(2 * pi * 164.8 * t) +
        .14 * sin(2 * pi * 220.0 * t)
    )

add_chime(1.71, [392, 523], .78, .058)
add_chime(3.56, [523, 659, 784], .75, .047)
for at in [5.98, 6.25, 6.52]:
    add_tick(at)
for at in [7.69, 9.19, 10.81, 12.23, 13.99, 15.45]:
    add_tick(at, high=True)
for at in [10.22, 13.41, 16.66]:
    add_tick(at, high=False)
add_chime(17.72, [392, 493.88, 587.33], 1.12, .086)
add_chime(18.90, [440, 554.37, 659.25], 1.15, .085)
add_chime(21.22, [440, 554.37, 659.25, 880], 1.75, .107)
add_chime(24.83, [523.25, 659.25, 784], 2.0, .092)

out = Path(__file__).resolve().parents[1] / 'assets' / 'logic-chimes.wav'
with wave.open(str(out), 'wb') as wav:
    wav.setnchannels(1)
    wav.setsampwidth(2)
    wav.setframerate(RATE)
    wav.writeframes(b''.join(struct.pack('<h', int(max(-1, min(1, tanh(v))) * 32767))
                             for v in buf))
print(f'Wrote {out}, {LENGTH:.1f}s, 24kHz mono, original synthesis.')
