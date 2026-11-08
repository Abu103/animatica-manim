# Animatica Studio UX: minimal, prompt-first workflow

**Status:** Approved direction from the user on 2026-11-07.

## Goal

Make `animatica tui` feel like a polished, modern product while retaining the
clarity and restraint of a classic terminal app. A first-time user should be
able to create a video without learning command-line flags, JSON, hidden
shortcuts, or provider terminology.

## Design

- Keep Textual; improve the interaction model rather than changing frameworks.
- Keep the existing four stages, but show one stage at a time with a clear
  progress header and visible Back / Continue actions. Do not expose tabs as the
  main navigation.
- Start prompt-first. Template and saved-storyboard paths are explicit alternate
  modes, not three simultaneous fields with an “exactly one” warning.
- Show a human-readable scene preview. Keep raw storyboard JSON in an
  **Advanced** disclosure.
- Put everyday choices behind recommended defaults; tuck provider, output,
  caption, lint, and other power controls into a clearly named advanced area.
- Render has one primary action, honest progress, a visible cancel action, and a
  clear success/recovery state.
- Use a restrained, classic-terminal palette, strong hierarchy, consistent
  spacing, and visible keyboard focus. Mouse and keyboard must both work; no
  keyboard shortcut is required to complete the flow.
- Preserve 80×24 minimum size, Windows support, saved defaults, output safety,
  and the existing real-work progress model.

## Reference patterns

- **Toad** and **OTerm**: prompt-first AI workflow and settings that do not
  require editing config files. Toad is a pattern reference only; its README
  currently says native Windows is unsupported.
- **Frogmouth** and **Toolong**: clear in-app help, obvious navigation, and
  mouse-plus-keyboard use.
- **Harlequin**: mature Textual component patterns, not its dense multi-pane IDE
  layout as the default experience.

References are inspirations; no source code is copied.

## Non-goals

- Building a browser/web interface or adding animation for its own sake.
- Removing advanced capabilities or changing the render pipeline.
- Replacing honest/indeterminate progress with guessed percentages.
- Adding the Vercel `skills` CLI or agent skill packs as Animatica runtime
  dependencies.

## Acceptance checks

- First screen explains what to do and has one obvious primary action.
- Alternate input modes cannot accidentally conflict with the prompt.
- Raw JSON and power settings are hidden until explicitly opened.
- Every step has visible navigation; help is discoverable in-app.
- The complete path is usable at 80×24 with keyboard and mouse.
- Existing rendering, cancellation, progress, output-warning, and error behavior
  continues to pass its regression tests.
