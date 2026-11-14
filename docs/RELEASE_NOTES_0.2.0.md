# v0.2.0 — draft release notes

Status: **draft for the owner to edit.** Not published. Source: `CHANGELOG.md`'s
`v0.2.0` section, written for a release page rather than a diff. Cut the tag
and paste the final text into the GitHub release once this looks right.

---

## Highlights

- **One-command sandbox setup.** `scripts/sandbox.sh` takes a bare machine
  (just `curl`, `tar`, `sh`) to a verified checkout with `animatica doctor`
  and a smoke render passing. The runtime it uses is prebuilt and published
  automatically whenever the dependency list changes.
- **A real eval harness.** `animatica eval` now takes `--model` /
  `provider:model`, has a recorded baseline and reference corpus, and
  `--save-dir` lets a live run be replayed later with no network — which is
  exactly what the new offline regression gate (`tests/test_eval_gate.py`)
  does in CI, against ten recorded storyboards.
- **A real gallery.** `scripts/render_gallery.py` renders every example
  storyboard and writes the results — including warnings, verbatim — into
  `docs/GALLERY.md`. `docs/VERIFIED_INSTALLS.md` is the place clean-machine
  install runs get logged.
- **CI got faster and stricter.** Both `linux` and `windows` are now split
  into a "run the suite" half and a "do the real installer/render checks"
  half that run in parallel, judged by a cheap aggregate job. The Windows
  TinyTeX cache now actually caches something (it had been pointed at an
  empty directory). Zero skips allowed on either platform.
- **Noticeably fewer rough edges.** A pass of real defects from `ruff` (110
  fixed), captions that overran their component's space, graph legends and
  tick labels drawn against the real caption, a parametric graph with
  mismatched axis scales, and several failure modes in `animatica eval`
  itself (network errors, a reasoning model running out of tokens, a model
  sending malformed JSON) that used to end in a bare traceback.

## Fixes worth knowing about if you hit them before

- Code components (`code_walkthrough`, `code_highlight`) now accept code
  whose newlines arrived double-escaped instead of mis-splitting it into one
  giant line.
- `extract_json` recovers from a reply a model cut off mid-object instead of
  failing opaquely.
- The prompt catalog now spells out field names for `compare`, `timeline` and
  `array_viz` instead of letting models guess them.

## Upgrading

No config or storyboard-format changes. Re-run `animatica doctor` after
pulling if you're on Windows — the TinyTeX cache fix means the first CI run
(or local bootstrap) after this release repopulates it from scratch.

## Known gaps

- `docs/VERIFIED_INSTALLS.md` is still empty — needs at least one real
  clean-machine report before it says anything.
- No narration / TTS yet (proposed for v0.3, needs a licensing check first).

---
*Draft generated from the CHANGELOG; edit freely before publishing.*
