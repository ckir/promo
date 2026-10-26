# promo review: one variant per screen (short design)

Status: DRAFT, awaiting owner approval. Owner waived the agy consult for this change (2026-10-26).
Size: small (one function and its loop, tests, two doc lines).

## Intent and why
`promo review` prints every variant of a draft as a boxed panel, then the prompt (`src/promo/review.py:155-158`).
Measured 2026-10-26 on the real clavity drafts: each variant panel is 15-27 lines at width 100, and a whole
draft screen is 42-87 lines (widths 80-120). A terminal shorter than that scrolls Variant 1 off the top, so the
owner picks without seeing every variant. The hint line also says `[1-9] choose` (`review.py:158`) though a
draft has `variants_per_draft` (3 today) variants.

## Decision (owner's)
Option 1 of three considered: one variant per screen, `n`/`p` to move, number keys still choose.
Other options, not chosen: fit-to-screen fallback (more code), fix the hint only (leaves the scrolling).

## Goals
- Each screen shows the draft header, the warnings for that screen's variant, ONE variant, and the key hint.
- The owner can see every variant and choose one without scrolling, on a terminal tall enough for the
  longest single variant.

## Non-goals
- Detecting the terminal height or paginating inside a variant. No new dependency, no curses, no pager.
- Changing the draft file format, `chosen`, approve/skip/edit/regenerate/copy semantics, or the non-TTY refusal.

## Anti-goals
- Approving a variant the owner never saw. Breaking an existing key.

## Decisions (my proposals; the owner can change any)
- **View state.** The loop holds `view` (1-based). It starts at the chosen variant if there is one, else 1, and
  resets the same way when the loop moves to the next draft or after regenerate (which clears `chosen`). After
  an edit it is clamped to `1..len(variants)`.
- **Keys.** `n` next and `p` previous, both wrapping around; they only move the view, work in every status
  (including approved drafts opened with `--all`), and never write the file. A digit `1..len(variants)`
  keeps its meaning (choose and save) and also moves the view to that variant, so the owner sees what was
  chosen. Out-of-range digits keep the existing `no variant N` error. All other keys are unchanged.
- **Screen.** Title `Variant N of M` plus `(chosen)` when it is the chosen one. Per-variant detail lines
  (`variant N matches:`, `variant N unsourced:`) are printed only for the viewed variant. Draft-level
  `warning:` lines stay. The hint is built from the real count:
  `[1-M] choose  n next  p prev  c copy  e edit  r regenerate  a approve  s skip  q quit`.
- **Single-variant drafts.** `n` and `p` are accepted and do nothing visible; the hint still lists them.
- **Unreadable draft.** Unchanged: `e`, `s`, `q` only.

## Known limit
One variant is up to ~27 lines at width 100 (a Facebook post can be 5000 characters), plus about 5 lines of
header and hint. A terminal under roughly 35 rows can still scroll the longest variant. This design does not
solve that; it removes the 3x stacking.

## Tests (the oracle for behaviour; existing tests that pin "all variants printed" change on purpose)
New or changed tests in `tests/test_review.py`: only the viewed variant's text is printed; `n`/`p` move and wrap;
a digit chooses, saves and moves the view; `n`/`p` write nothing; the hint shows the real count; per-variant
warning lines appear only for the viewed variant; view starts at the chosen variant; view resets after
regenerate and is clamped after an edit that removes variants.

## Docs
`README.md:32` (the Keys sentence) and `docs/superpowers/specs/2026-10-24-promo-agent-design.md:144` (the Keys
line) get the new keys.

## Left to the builder
Where `view` lives (a local in `review()` passed to `_show`); the exact strings beyond those above.

## Self-audit
Closed: key semantics, view lifecycle, wrapping, single-variant case, status interactions, doc locations.
Open, resolved at implementation: which existing tests break (found by running the suite after the change).
Unsolved by design: terminals shorter than the longest variant (stated above).
