# Improvement plan (from the Fibonacci out1 review, 2026-11-04)

## Done in this patch
- Raw LaTeX on screen: root cause = incomplete TeX install (missing standalone.cls, babel-english). Fixed code-side fallback + doctor + clear fix message. User-side fix: tlmgr line in README.
- No ball existed: added `bounce_sequence`. Prompt tells the model to use it.
- Diagram off-centre/clipped, caption drift (diagram 6.4s declared vs ~7.1s real), equation transform timing.
- Warnings invisible, --preview ignored, template hijacking explicit --provider, "square" matching "mc squared".
- 216 tests pass (190 before).

## Not verified
- Windows run, live NIM call, tlmgr package names on a real TinyTeX.
- Model quality: nemotron picks components from a fixed list of 9. Re-run your original prompt and check it uses bounce_sequence.

## Next (before showing others)
1. Run your prompt end to end on your machine; keep 3-4 good outputs as a demo gallery (README gif/mp4 links).
2. Offline templates: label as examples or fill from prompt words.
3. Bar chart: tiny values (0-3 vs max 55) are invisible. Add min height or log scale option.
4. Smoke test in CI (GitHub Actions: doctor + one render).
5. Pin manim version, document it.

## Later (your ideas go here)
- Narration/TTS, more generic visual primitives (moving dot on a path, number line, tree), web UI.
- Generic "primitive" layer so the LLM composes shapes instead of picking fixed components. Biggest quality jump, biggest rewrite.

