# Narration: offline TTS timed to captions

Date: 2026-11-14 · Base: `main` @ `a54a93b` · Status: proposed (not approved) · Path: architectural

## 1. Problem and success criteria

A video today has burned-in captions but no voice. `docs/TASKS_FOR_HERMES_V02.md`
proposes a `--narrate` flag using Piper, flagged UNVERIFIED on licensing. That's
now checked (section 2): resolved, with one constraint on which voice ships by
default.

Done when:

1. `animatica make "<prompt>" -o out/ --narrate` produces an MP4 with narration
   audio muxed in, using the exact text already in each beat's caption
   (`beat.caption or comp.fallback_text(params)` — the same string
   `_write_captions` already puts in `captions.vtt`).
2. No video desyncs: a beat's visual and its narration start together. See
   section 3 for what "sync" means when the two don't naturally take the same
   time.
3. Offline and CPU-only, matching the rest of the pipeline's no-GPU,
   no-mandatory-network stance. No new mandatory network call at render time.
4. `--narrate` is opt-in. Every existing test, gallery storyboard and CLI
   invocation without the flag is byte-for-byte unaffected.
5. Doctor checks narration deps the same way it checks LaTeX: reports missing,
   `--fix` installs.

Non-goals: voice cloning, SSML, per-beat voice switching, multi-speaker
dialogue, any paid/cloud TTS provider.

## 2. Licensing — resolved

Checked against the upstream `rhasspy/piper-voices` MODEL_CARD data (not
third-party resellers, which overstate the restriction — e.g. tts.ai markets
most voices as "personal use only" to upsell its own commercial tier; that is
not what the MODEL_CARDs say):

- **The Piper engine itself is MIT-licensed.** Fully commercial-safe, no
  attribution burden, matches every other dependency's license posture.
- **Each voice model carries its own license** (inherited from the speech
  corpus it was trained on). This varies per voice:
  - `en_US-ljspeech-high` / `en_US-ljspeech-medium` — **public domain**
    (LJSpeech corpus). No attribution needed. **Recommend this as the default
    bundled voice.**
  - `en_US-libritts-high` — CC BY 4.0 (attribution required; fine for an
    about/credits line, more friction for a silent default).
  - `en_US-kathleen-low` — CC0.
  - Other voices range further, including some genuinely non-commercial ones
    — a voice must be checked individually before it's offered as a default,
    not assumed clean because the engine is.

Action: ship `en_US-ljspeech-medium` as the default bundled voice (public
domain, decent quality, small file). A `--voice <name>` flag can expose other
Piper voices later, each gated by checking its MODEL_CARD before it's added
to the allowlist — same "fails closed on an unverified hash" posture as the
Windows TeX bundle.

## 3. Sync strategy — the actual design decision

Today, a beat's on-screen duration comes from `comp.duration(params)`: a pure
function of the component's params, computed once in `_beat_durations`
(`pipeline.py`), independent of any audio. Adding narration means one beat now
has two independently-determined durations: the visual's and the narration
clip's. They won't usually match.

Three options:

- **(a) Speed up/slow down the narration audio to fit the visual's duration.**
  Rejected: Piper audio resampled more than ~10-15% starts sounding wrong, and
  a caption-driven narration script has no reason to land inside whatever
  duration the component's `duration()` happened to compute.
- **(b) Speed up/slow down the visual to fit the narration.** Rejected: the
  per-component `duration()` functions are tuned for readability (e.g. a
  `bounce_sequence` term needs enough time to register), and components don't
  currently support an external duration override — this would touch every
  component.
- **(c) Extend the beat to `max(visual_duration, narration_duration)`,
  holding the component's resting frame for the difference.** **Recommended.**
  Every component already has a notion of entering, doing its thing, and a
  natural matching `fallback_text()`/final state — holding that final frame
  costs nothing architecturally (`play()` already returns after drawing;
  padding is extra wait time, not new animation code). This is the same shape
  as the existing timing-warning gate (`ci_render_gate.py` already fails on a
  beat that "ran longer than it declared" — here the beat *declares* longer
  on purpose, instead of drifting unintentionally).

(c) means: synthesize narration audio for every beat first (per the text
`_write_captions` already derives), measure each clip's length, feed those
lengths into `_beat_durations` as a per-beat floor, then render as today. The
render pipeline's timing math doesn't change; it gets one more input.

## 4. Where this lands in the pipeline

- New `src/animatica/narration.py`: `synthesize(text: str, voice: str) -> Path`
  (wraps the Piper CLI/binding, writes a WAV), plus a `narrate_storyboard(sb,
  registry) -> list[Path | None]` that reuses the same per-beat text
  `_write_captions` computes (do not re-derive it twice — refactor that text
  lookup into a shared helper both call).
- `_beat_durations` takes an optional `narration_durations: list[list[float]]`
  and does the `max()` per beat.
- `make_video` muxes the per-beat WAVs into one track aligned to the final
  per-beat timing, via the existing ffmpeg path (`imageio-ffmpeg` is already a
  dependency; no new native dep beyond Piper itself).
- `doctor`: new check, same pattern as the LaTeX check — reports Piper binary
  + default voice file present/missing; `--fix` downloads the MIT-engine
  binary and the public-domain default voice, verified against a pinned
  sha256 (same fail-closed posture as the Windows TeX bundle: not fetched at
  all while the expected hash is unknown).
- `report.json`: records which voice was used and its license, so a user who
  ships the output video knows what they're bound by without re-deriving it.

## 5. What's not decided here (owner input needed)

- Is a ~60MB default voice model an acceptable addition to a "one command,
  under a minute" install promise (section 1 of the sandbox spec), or does it
  need to be fetched lazily only when `--narrate` is first used?
- `--voice` exposed in 0.3, or default-only until there's a second
  verified-license voice worth offering?

## 6. Non-goals, restated

No SSML, no cloning, no cloud providers, no per-beat voice override. A
narrated video is not required to sound different from the burned-in caption
text — narration reads the caption, it doesn't get its own script.
