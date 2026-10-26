# promo review: one variant per screen Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `promo review` shows one variant per screen, with `n`/`p` to move between variants, so a draft fits a normal terminal.

**Architecture:** `review()` in `src/promo/review.py` keeps a 1-based `view` index per draft and passes it to `_show`, which prints the header, that variant's warning detail, one panel and a hint built from the real variant count. No change to draft files, the `ReviewIO` protocol or any other key.

**Tech Stack:** Python >=3.12, rich (already used), pytest, ruff, mypy (`src` only).

**Spec:** `docs/superpowers/specs/2026-10-26-review-one-variant-per-screen-design.md` (approved by the owner 2026-10-26; agy waived by the owner).

## Global Constraints

- Only `src/promo/review.py` changes in `src/`. No new dependency. `ReviewIO` (`review.py:51-56`) is unchanged.
- Existing keys keep their meaning: `1`..`9` choose and save, `c`, `e`, `r`, `a`, `s`, `q`. Out-of-range digits keep the error `no variant N`. An unreadable draft still accepts only `e`, `s`, `q`.
- `n` next and `p` previous: wrap around, never write the file, work in every status (including approved drafts under `--all`), and are refused like any key on an unreadable draft.
- A digit that is accepted (draft status, in range) also moves the view to that variant.
- Per-variant detail lines (`variant N matches:`, `variant N unsourced:`) print only for the viewed variant. Draft-level `warning:` lines and the media hint stay.
- Title text: `Variant N of M`, plus ` (chosen)` when N is the chosen variant.
- Hint text with M variants (M >= 2): `[1-M] choose  n next  p prev  c copy  e edit  r regenerate  a approve  s skip  q quit`. With M == 1 the first token is `[1] choose` (my call: `[1-1]` reads badly; the spec says only "built from the real count").
- `just check` (lint, typecheck, license, test) stays green. New test code carries no new licence-header work (edits are inside an existing file).

## Review Focus

1. Opening a draft whose chosen variant is not 1 must show the chosen one, not variant 1 (`test_view_starts_at_the_chosen_variant`).
2. After regenerate (which clears `chosen`, possibly changes the variant count) the view returns to variant 1 (`test_view_resets_after_regenerate`).
3. After an edit that removes variants, the view must not point past the end (`test_view_is_clamped_when_an_edit_removes_variants`).
4. `n`/`p` on an already-approved draft must work, while digits stay blocked there (`test_n_and_p_work_on_an_approved_draft`).
5. Hostile text in variant 2 (markup, escape bytes) must still be neutralised when it is the viewed variant (`test_markup_and_escape_sequences_in_variants_are_neutralised`, changed to press `n`).

---

### Task 1: One variant per screen, `n`/`p`, and the docs

**Files:**
- Modify: `src/promo/review.py:131-158` (`_show`), `src/promo/review.py:161-248` (`review` loop; all line numbers verified 2026-10-26)
- Modify: `tests/test_review.py` (add tests after `test_warning_details_and_media_hint`, line 254; change `test_markup_and_escape_sequences_in_variants_are_neutralised`, line 233)
- Modify: `README.md:32`, `docs/superpowers/specs/2026-10-24-promo-agent-design.md:144`

**Interfaces:**
- Consumes (exist now): `Draft` (`.meta` with `.chosen: int | None`, `.status`, `.id`, `.warnings`; `.variants: list[str]`, guaranteed non-empty and equal to `meta.variants` by `drafts.load`); `ReviewIO.print/read_key/read_line`; `tag_links`, `prohibited_matches`, `unsourced_numbers`, `sanitize`; test helpers `ScriptedIO`, `_run`, and fixture `drafts_tree` (conftest) whose drafts have 3 variants texts `"<name> one"`, `"<name> two"`, `"<name> three"` and review order `approved_warn`, `draft_warn`, `draft`.
- Produces: `_show(io: ReviewIO, draft: Draft, manifest: Manifest, view: int) -> None` (`view` is 1-based and valid; the only caller is `review()`); `_hint(count: int) -> str`; `_initial_view(draft: Draft) -> int` (the chosen variant, else 1).

- [ ] **Step 1: Write the failing tests** in `tests/test_review.py`. Names and assertions (use `ScriptedIO`, `_run`, `drafts`, `Status` as the file already does; the file's existing imports cover them):

```python
def test_only_the_viewed_variant_is_printed(drafts_tree):
    io = ScriptedIO(["s", "s", "q"])
    _run(drafts_tree, io)
    assert "draft one" in io.output
    assert "draft two" not in io.output and "draft three" not in io.output
    assert "Variant 1 of 3" in io.output

def test_hint_shows_the_real_variant_count(drafts_tree):
    io = ScriptedIO(["s", "s", "q"])
    _run(drafts_tree, io)
    assert "[1-3] choose  n next  p prev" in io.output
    assert "[1-9]" not in io.output

def test_n_moves_forward_and_wraps(drafts_tree):
    io = ScriptedIO(["s", "s", "n", "n", "n", "q"])
    _run(drafts_tree, io)
    assert "draft two" in io.output and "draft three" in io.output
    # 3 first screens (approved_warn, draft_warn, draft) + 1 after wrapping on `draft`
    assert io.output.count("Variant 1 of 3") == 4

def test_p_moves_back_and_wraps(drafts_tree):
    io = ScriptedIO(["s", "s", "p", "q"])
    _run(drafts_tree, io)
    assert "draft three" in io.output and "Variant 3 of 3" in io.output

def test_n_and_p_write_nothing(drafts_tree):
    path = drafts_tree.paths["draft"]
    before = (path.read_bytes(), path.stat().st_mtime_ns)
    _run(drafts_tree, ScriptedIO(["s", "s", "n", "p", "q"]))
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before

def test_digit_chooses_and_moves_the_view(drafts_tree):
    io = ScriptedIO(["s", "s", "2", "q"])
    _run(drafts_tree, io)
    assert drafts.load(drafts_tree.paths["draft"]).meta.chosen == 2
    assert "Variant 2 of 3 (chosen)" in io.output and "draft two" in io.output

def test_view_starts_at_the_chosen_variant(drafts_tree):
    d = drafts.load(drafts_tree.paths["draft"]); d.meta.chosen = 3; drafts.save(d)
    io = ScriptedIO(["s", "s", "q"])
    _run(drafts_tree, io)
    assert "Variant 3 of 3 (chosen)" in io.output
    assert "draft one" not in io.output

def test_warning_detail_lines_only_for_the_viewed_variant(drafts_tree):
    path = drafts_tree.paths["draft_warn"]
    d = drafts.load(path)
    d.variants[0] = "This is guaranteed to work"
    d.variants[1] = "It works in 99 ways"
    d.meta.warnings = ["prohibited_claim", "unsourced_number"]
    drafts.save(d)
    first = ScriptedIO(["s", "q"]); _run(drafts_tree, first)
    assert "variant 1 matches: guaranteed" in first.output
    assert "variant 2 unsourced" not in first.output
    second = ScriptedIO(["s", "n", "q"]); _run(drafts_tree, second)
    assert "variant 2 unsourced: 99" in second.output

def test_n_and_p_work_on_an_approved_draft(drafts_tree):
    io = ScriptedIO(["n", "q"])  # first draft in order is approved_warn
    _run(drafts_tree, io)
    assert "approved_warn two" in io.output
    assert "promo unapprove" not in io.output

def test_view_resets_after_regenerate(drafts_tree):
    gen = FakeGenerator(responses=[["fresh one", "fresh two", "fresh three"]])
    io = ScriptedIO(["s", "s", "n", "r", "q"], ["a note"])
    _run(drafts_tree, io, generator=gen)
    assert "fresh one" in io.output and "fresh two" not in io.output

def test_view_is_clamped_when_an_edit_removes_variants(drafts_tree):
    def shrink(path):
        d = drafts.load(path); d.variants = ["only one"]; d.meta.variants = 1
        d.meta.chosen = None; drafts.save(d)
    io = ScriptedIO(["s", "s", "n", "n", "e", "q"], edit=shrink)
    _run(drafts_tree, io)
    assert "Variant 1 of 1" in io.output and "only one" in io.output
    assert "[1] choose" in io.output
```

Also change `test_markup_and_escape_sequences_in_variants_are_neutralised` (line 241): its keys become `["s", "s", "n", "q"]` so that variant 2 (the hostile `evil ...` text) is the viewed variant; its assertions are unchanged. Add type annotations (`drafts_tree: DraftsTree`, `-> None`, `path: Path`) as the sibling tests have.

- [ ] **Step 2: Run the new and changed tests to verify they fail**

Run: `uv run pytest tests/test_review.py -q`
Expected: the new tests FAIL (all three variants are still printed, no `n`/`p`, no `Variant N of M`) and `test_markup_and_escape_sequences_in_variants_are_neutralised` still passes or fails only for the new key. If a new test passes before any code change, it is a finding about the test; fix the test.

- [ ] **Step 3: Implement in `src/promo/review.py`**
  - `_hint(count: int) -> str` returns the Global Constraints hint (M == 1 uses `[1]`).
  - `_initial_view(draft: Draft) -> int` returns `draft.meta.chosen` if not None, else 1.
  - `_show(io, draft, manifest, view)`: keep the header line, draft-level `warning:` lines and the media hint; compute the per-variant `matches`/`unsourced` lines for `draft.variants[view - 1]` only (same texts as now, numbered `view`); print ONE `Panel` titled `Variant {view} of {len(draft.variants)}` plus `(chosen)` when `meta.chosen == view`; print `_hint(len(draft.variants))`.
  - `review()`: per draft, hold `view: int | None = None` (new for each draft in the outer `for`). Each time a readable draft is loaded, if `view is None` set it to `_initial_view(draft)`, then clamp it to `1..len(draft.variants)`, then call `_show(..., view)`. After the unreadable-draft guard (`review.py:196-198`) and before the status block (`review.py:199`), handle `n`/`p`: `view` becomes the next/previous index with wrap-around (modulo `len(draft.variants)`), then `continue`. After an accepted digit and a successful `drafts.save`, set `view = n`. After a successful `regenerate_one`, set `view = None`.
  - mypy (`just typecheck`) covers `src`; keep full annotations.

- [ ] **Step 4: Run the review tests, then the whole suite**

Run: `uv run pytest tests/test_review.py -q` then `just check`
Expected: all tests in `tests/test_review.py` pass (the pre-existing ones still pass except as already changed in Step 1). Then `just check` ends with all passed. The suite was 262 passed before this work; expect 273 (262 + 11 new tests).
If an unchanged pre-existing test fails, do not edit it to fit: it pins behaviour the spec keeps, so the code is wrong.

- [ ] **Step 5: Mutation check** on the two tests that guard the riskiest behaviour. Temporarily (and then restore) (a) make `n` not wrap and (b) make the loop ignore `_initial_view` (always start at 1). Run `uv run pytest tests/test_review.py -q`.
Expected: `test_n_moves_forward_and_wraps` fails for (a) and `test_view_starts_at_the_chosen_variant` fails for (b). Restore both and re-run until green.

- [ ] **Step 6: Update the docs.** In `README.md:32` change the Keys sentence to: `Keys: 1-9 choose a variant (up to the number of variants shown), n next and p previous variant, c copy, e edit, r regenerate with a note, a approve, s skip, q quit.` and add that one variant is shown at a time. In `docs/superpowers/specs/2026-10-24-promo-agent-design.md:144` (the review bullet) change "Shows the variants rendered with rich" to "Shows one variant per screen, rendered with rich" and add `n`/`p` to the Keys list in that bullet. Do not touch any other line.

- [ ] **Step 7: Run the gate and commit**

Run: `just format && just check`
Expected: last line `273 passed`, exit 0.

```bash
git add src/promo/review.py tests/test_review.py README.md docs/superpowers/specs/2026-10-24-promo-agent-design.md
git commit -m "feat: show one variant per screen in promo review"
```

- [ ] **Step 8 (owner, after merge): try it on the real drafts** in a normal terminal: `uv run promo review clavity`. Expected: one variant per screen, `n`/`p` move, the hint reads `[1-3]`. A terminal under about 35 rows can still scroll the longest variant (spec: Known limit).

---

## Self-review (run 2026-10-26)

- **Spec coverage:** view state and its three resets (initial/chosen, regenerate, edit-clamp) -> Step 3 and tests 7, 10, 11; keys `n`/`p`, wrap, no write, any status -> tests 3, 4, 5, 9; digit chooses and moves view -> test 6; title and hint with real count -> tests 1, 2 and 11 (`[1]`); per-variant detail lines only for the viewed variant -> test 8; single-variant draft -> test 11; unreadable draft unchanged -> existing `test_broken_file_only_accepts_e_s_q` (not edited); docs -> Step 6; the existing test that assumed all variants printed -> changed in Step 1 and named.
- **Gaps left, with where they resolve:** the exact status of `n`/`p` when a digit would be refused is covered by test 9; the "known limit" (terminals under ~35 rows) is stated in the spec and not solved; the owner's real-terminal check is Step 8 (owner-run).
- **Placeholders:** none. The test bodies are given because the assertions are the decisions; the implementation is given as signatures and behaviour only.
- **Types:** `_show(..., view: int)`, `_hint(count: int) -> str`, `_initial_view(draft: Draft) -> int` are used consistently in Step 3. Citations checked against the files on 2026-10-26: `review.py:131-158`, `161-248`, `196-198`, `199`; `test_review.py:233`, `254`; README line 32; promo design spec line 144; `drafts.load` rejects a variant-count mismatch (`drafts.py:165`).
- **Proportion:** the plan is longer than the spec because the tests carry the assertions; the code body is left to the implementer.
