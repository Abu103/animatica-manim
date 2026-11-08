# Hermes playbook for Animatica

How to run Hermes + Nemotron so it behaves like a disciplined senior engineer on this repo, and where it still needs Claude. Everything marked UNVERIFIED must be checked on your machine before you rely on it.

## 1. The honest premise

A free 120B model will not match a frontier model on open-ended reasoning. What closes most of the gap is not a cleverer prompt, it is the harness around the model:

- Tasks small enough to hold in context (one card, <=5 files).
- Deterministic gates the model cannot talk its way past (tests, `scripts/ci_tests.py`, CI).
- Evidence before edits (real logs, not guesses).
- A hard stop after two failures, and a handoff to a stronger model.
- Skills and AGENTS.md that put the senior-engineer habits into every session.

Expect Hermes to be good at: components from the scaffold, tests, docs, gallery and eval runs, mechanical refactors with tests, small bug fixes with a clear failing test.
Expect it to struggle with: cross-file design, async/platform-specific bugs, long-horizon planning, noticing its own mistakes. Route those to Claude (section 5).

## 2. One-time setup (WSL)

Hermes' own docs say native Windows is experimental; you already work in WSL, keep doing that.

1. Install: `curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash`
2. Provider: run `hermes model`. Your log records provider NIM with model `nvidia/nemotron-3.5-super-vl-120b-a12b`. NIM's OpenAI-compatible base URL is `https://integrate.api.nvidia.com/v1` (confirmed in NVIDIA's own blog). Keep keys only in `~/.hermes/.env`.
3. Sampling: ROADMAP.md quotes temperature 1.0, top_p 0.95 from third-party guides. UNVERIFIED against the model card. If you see malformed tool calls, try a lower temperature (0.2-0.6) for coding sessions and compare on one card.
4. Install this pack: from the repo root run `bash /path/to/hermes-pack/install.sh`. It copies AGENTS.md and the two docs into the repo and the skills into `~/.hermes/skills/animatica-process/`.
5. Check skills load: in Hermes `/reload-skills`, then ask "what skills do you have?" (or `hermes chat --toolsets skills -q "What skills do you have?"`). You should see the nine skills plus the repo's `skills/animatica`.
6. Make the repo skill visible too: add to `~/.hermes/config.yaml`:
   ```
   skills:
     external_dirs:
       - ~/animatica-manim/skills
   ```
   (the `external_dirs` key is from Hermes' skills docs).
7. CI log access: `gh auth login` once in WSL. This is the single biggest time-saver; most wasted hours came from guessing without the log.
8. Context file: Hermes reads `AGENTS.md`, `.hermes.md` or `CLAUDE.md` as project rules. AGENTS.md is in the repo root after step 4. Confirm by asking "what are the non-negotiable rules for this repo?".
9. Add `.hermes/` to `.gitignore` (plans live in `.hermes/plans/`).

## 3. The loop every card follows

```
Intake -> Plan -> [Gate A] -> Red test -> Green -> Verify -> Self-review -> Commit locally -> Report -> [Gate B]
```

- Intake: skill `task-intake`. Restate goal, files, acceptance command.
- Plan: `/plan` for anything NORMAL. Gate A: you (or Claude) say "approved". Trivial cards skip the gate.
- Build: skills `tdd-loop`, `cross-platform-tui-tests`. Failures: `evidence-first-debugging`, `ci-log-triage`.
- Verify: skill `verify-before-claiming`. Report lists Verified and NOT verified separately.
- Commit: skill `git-branch-discipline`. Local commits only.
- Gate B: at milestone ends and after two strikes, a Claude review via a handoff packet (section 6). Push only after your yes.

Start a fresh Hermes session for each card. Long sessions drift; the files on disk are the memory, not the chat.

## 4. Card sizing (what keeps a weaker model reliable)

- <=5 files, ~150 changed lines, exactly one acceptance command.
- Every card names: files to touch, the pattern file to copy, the acceptance command, and what "done" looks like.
- If a card needs a design choice, it is not a card yet; send it to Claude first.
- Never ask for "implement the roadmap". Ask for T-number.

## 5. Who does what

| Work | Owner |
|---|---|
| New components, tests, docs, gallery, eval runs, small fixes with failing test | Hermes |
| Specs, schema or CLI changes, installer/CI design, anything cross-platform and subtle | Claude drafts, Hermes implements |
| Debugging after two strikes, reviewing a milestone diff | Claude |
| Approve push, merge, tag, release | You |

## 6. Handoff packet and escalation

Use the `milestone-handoff` skill. Paste its output to Claude with one question. A good packet contains verbatim failing output and every failed attempt; that is what lets a reviewer find the cause in one pass instead of five.

Escalate when: two strikes, a card grows past its size limit, the acceptance command cannot run in your environment, or the task needs a design decision.

## 7. Failure modes and countermeasures

| Failure | Countermeasure already in the pack |
|---|---|
| Says "done" without running anything | `verify-before-claiming`: paste output; list unverified |
| Edits or skips tests to get green | AGENTS rule 4; reviewer checks `git diff tests/` first |
| Loops on variations of one fix | Two-strike rule |
| Touches unrelated files | Card file list; `git diff --stat` check |
| Hallucinated APIs/flags/paths/URLs | Rule 8: read source, `--help`, fetch links |
| Fixes the wrong run/commit | `ci-log-triage` checks the SHA |
| Treats upstream 5xx as a code bug | `ci-log-triage` pitfall; bounded retries |
| "Works on Windows" from a Linux run | Cross-platform skill: Windows unverified until CI green |
| Huge diffs | Size limit; stop and say so |
| Drifting in a long session | One session per card |

## 8. Prompts to paste

Start of every session:
```
Read AGENTS.md. Use skill task-intake. Card: T<N> in docs/TASKS_FOR_HERMES_V02.md.
Restate goal, files, acceptance command. If NORMAL, write the plan with /plan and wait for my "approved".
```

Mid-task failure:
```
Stop editing. Use skill ci-log-triage / evidence-first-debugging. Show me the verbatim first error and your hypotheses with the cheap check for each. Do not change code until I reply.
```

End of card:
```
Use skill verify-before-claiming. Run the acceptance command and python scripts/ci_tests.py. Report Changed / Verified / NOT verified / Risks. Do not push.
```

Two strikes hit:
```
Use skill milestone-handoff. Write the packet with the verbatim failing output and every attempt, then stop.
```

Review request to Claude (paste with the packet):
```
Review this Animatica handoff. Find the root cause or the flaw in the diff. Be concrete: name the file and line, say what you verified versus infer, and give the smallest fix plus a regression test.
```

## 9. Measuring whether it works

In `docs/SESSION_TASKS.md` record per card: first-try pass (yes/no), number of strikes, minutes, escalated (yes/no). After 5 cards: if first-try pass is under 60%, make cards smaller or try another model from your free list (OpenCode Zen free models, Nous Portal free models; free-tier availability changes, check before relying). Keep the eval harness as the objective model benchmark: `animatica eval --models a,b` on `tests/reference_prompts.txt`.

## 10. The path

Follow `docs/TASKS_FOR_HERMES_V02.md` in order. Milestone gates need a Claude review and your approval before the next milestone starts:

- M0 Housekeeping -> M1 Reliability (Windows TeX, TUI/graph fixes) -> M2 Evidence (eval baseline) -> M3 Showcase (gallery, verified installs) -> M4 Release 0.2.0 -> then v0.3 cards, after you approve the roadmap.
