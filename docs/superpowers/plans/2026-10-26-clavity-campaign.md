# clavity install campaign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `clavity` campaign to promo (manifest, brand voice, pinning tests) so `promo draft clavity` produces three Facebook drafts for hand posting.

**Architecture:** Data only. No change under `src/`. A new `campaigns/clavity/` holds `manifest.yaml` and `brand.md`; one new test file pins the spec's decisions against the real promo loaders and post-processing, so a later edit cannot reintroduce the contradiction the spec's panel round found.

**Tech Stack:** Python >=3.12, uv, pytest, ruff, `addlicense` (all already in the repo's `just check`).

**Spec:** `docs/superpowers/specs/2026-10-26-clavity-campaign-design.md` (approved by the owner 2026-10-26; agy escalation waived by the owner).

## Global Constraints

- No file under `src/` changes. `just check` (lint, typecheck, license, test) must stay green.
- New `.yaml` and `.py` files start with the repo's licence header, copied from `campaigns/example/manifest.yaml` lines 1-5 (`# Copyright (c) 2026 Costas Kirgoussios` ... `https://polyformproject.org/licenses/noncommercial/1.0.0/`). Markdown files carry no header (the existing `brand.md` has none).
- `network` is `facebook` only; every beat has `offset_days: 0`; `launch_date: 2026-11-02` (the owner may change it freely).
- `disclosures` is exactly `["I'm the author of clavity."]`.
- `prohibited_claims` is exactly: `completely free`, `free for any use`, `catches every bug`, `no bugs`, `independently verified`, `guaranteed`, `production-ready`.
- promo's `prohibited_matches` is a case-insensitive substring test with no negation handling (`src/promo/postprocess.py`, `p.lower() in lowered`): no required-wording phrase may contain a prohibited phrase.
- `confidential: false`. `brand_voice: campaigns/clavity/brand.md` (path is relative to where `promo` runs; `src/promo/schema.py` keeps it as given).
- Install commands are reproduced exactly from `/home/user/Development/Rust/clavity/README.md` (clavity commit `7a6910e8`): `claude plugin marketplace add ckir/clavity`, `claude plugin install clavity@clavity`, and the add-ons `agy-autotrain@clavity`, `commonmemory@clavity`, `review-relay@clavity`.

## Review Focus

Failure modes the spec implies that a person posting would hit:

1. A required-wording phrase that also appears in `prohibited_claims` (every honest draft would carry a `prohibited_claim` warning). Pinned in Task 1 by `test_required_wording_does_not_trip_prohibited_claims`.
2. A brand-voice example that itself fails promo's checks (too long, unsourced number, prohibited phrase), teaching the model a bad pattern. Pinned by `test_brand_examples_pass_post_processing`.
3. The case-study draft carrying a link or install command. promo cannot enforce this per beat; pinned only as an instruction in the beat's notes (`test_case_study_notes_forbid_links`), plus the owner's checklist item 6 in Task 2.
4. The install commands being paraphrased by the model. Pinned as exact strings in the beat's notes (`test_install_comment_notes_carry_exact_commands`); the model's output is still checked by the owner (Task 2).
5. A manifest or brand file that fails to load (missing markers, bad beat id), which would break `promo draft clavity` at the first run. Pinned by `test_manifest_shape` and `test_dry_run_counts_three_calls`.

---

### Task 1: The clavity campaign data and its pinning tests

**Files:**
- Create: `campaigns/clavity/manifest.yaml`
- Create: `campaigns/clavity/brand.md`
- Test: `tests/test_clavity_campaign.py`

**Interfaces:**
- Consumes (all exist now, verified 2026-10-26):
  - `promo.schema.load_manifest(path: Path) -> Manifest`; `Manifest.product`, `.beats`, `.brand_voice`, `.confidential`; `Beat.id/.intent/.networks/.offset_days/.notes`; enums `Network.facebook`, `Intent.deep_dive`, `Intent.custom`.
  - `promo.prompts.load_brand_voice(path: Path) -> tuple[str, str]` returns `(prose, examples)`; needs `<!-- promo:examples:start -->` and `<!-- promo:examples:end -->` in the file.
  - `promo.postprocess.finalize(text, *, manifest, beat, network, campaign, limit, hashtag_cap) -> tuple[str, list[str]]` and `prohibited_matches(text: str, phrases: list[str]) -> list[str]`.
  - `promo.networks.LIMITS`, `HASHTAG_CAPS` (dicts keyed by `Network`; Facebook is 5000 and 5).
  - CLI: `promo.cli.app`; `draft <campaign> --dry-run` prints `dry run: N model call(s) would be made`; it reads `campaigns/<campaign>/manifest.yaml` relative to the working directory (`src/promo/cli.py:80`).
- Produces: the campaign id `clavity`, with draft ids `clavity/case-study/facebook`, `clavity/install-comment/facebook`, `clavity/addon-replies/facebook`. Task 2 uses these.

- [ ] **Step 1: Commit the approved spec and this plan**

```bash
git add docs/superpowers/specs/2026-10-26-clavity-campaign-design.md docs/superpowers/plans/2026-10-26-clavity-campaign.md
git commit -m "docs: add clavity campaign design and plan"
```

- [ ] **Step 2: Write the failing tests** in `tests/test_clavity_campaign.py` (licence header first). Names and assertions:

```python
REPO = Path(__file__).parent.parent
CAMPAIGN = REPO / "campaigns" / "clavity"
PROHIBITED = {"completely free", "free for any use", "catches every bug", "no bugs",
              "independently verified", "guaranteed", "production-ready"}

def _beats(m): return {b.id: b for b in m.beats}

def test_manifest_shape() -> None:
    m = load_manifest(CAMPAIGN / "manifest.yaml")
    beats = _beats(m)
    assert list(beats) == ["case-study", "install-comment", "addon-replies"]
    assert beats["case-study"].intent is Intent.deep_dive
    assert beats["install-comment"].intent is Intent.custom
    assert beats["addon-replies"].intent is Intent.custom
    assert all(b.networks == [Network.facebook] and b.offset_days == 0 for b in m.beats)
    assert m.confidential is False
    assert m.product.target_url == "https://github.com/ckir/clavity"
    assert m.product.disclosures == ["I'm the author of clavity."]
    assert set(m.product.prohibited_claims) == PROHIBITED

def test_proof_points_carry_the_ledger_figures() -> None:
    joined = "\n".join(load_manifest(CAMPAIGN / "manifest.yaml").product.proof_points)
    for needle in ("3adc045", "KEEP=5 kept 4 slots", "KEEP=0, abc and -1 kept 0", "tail -n +1"):
        assert needle in joined

REQUIRED = {
    "case-study": ("own ledger", "one example", "not a rate"),
    "install-comment": ("superpowers", "Antigravity", "PolyForm Noncommercial 1.0.0",
                        "personal, academic and non-profit use only", "mutually exclusive"),
}

def test_required_wording_does_not_trip_prohibited_claims() -> None:
    m = load_manifest(CAMPAIGN / "manifest.yaml")
    for beat_id, phrases in REQUIRED.items():
        notes = _beats(m)[beat_id].notes or ""
        for phrase in phrases:
            assert phrase in notes, (beat_id, phrase)
            assert prohibited_matches(phrase, m.product.prohibited_claims) == [], phrase

def test_case_study_notes_forbid_links() -> None:
    notes = _beats(load_manifest(CAMPAIGN / "manifest.yaml"))["case-study"].notes or ""
    assert "Do not include any link or install command" in notes

def test_install_comment_notes_carry_exact_commands() -> None:
    notes = _beats(load_manifest(CAMPAIGN / "manifest.yaml"))["install-comment"].notes or ""
    assert "claude plugin marketplace add ckir/clavity" in notes
    assert "claude plugin install clavity@clavity" in notes

def test_addon_notes_name_the_three_plugins() -> None:
    notes = _beats(load_manifest(CAMPAIGN / "manifest.yaml"))["addon-replies"].notes or ""
    for plugin in ("agy-autotrain", "commonmemory", "review-relay"):
        assert f"claude plugin install {plugin}@clavity" in notes

def test_brand_examples_pass_post_processing() -> None:
    m = load_manifest(CAMPAIGN / "manifest.yaml")
    _, examples = load_brand_voice(REPO / m.brand_voice)
    lines = [ln for ln in examples.splitlines() if ln.strip()]
    assert lines
    for line in lines:
        text, warnings = finalize(
            line, manifest=m, beat=_beats(m)["case-study"], network=Network.facebook,
            campaign="clavity", limit=LIMITS[Network.facebook],
            hashtag_cap=HASHTAG_CAPS[Network.facebook])
        assert warnings == [], (line, warnings)
        assert "I'm the author of clavity." in text

def test_dry_run_counts_three_calls(tmp_path, monkeypatch) -> None:
    shutil.copy(REPO / "promo.toml", tmp_path / "promo.toml")
    shutil.copytree(CAMPAIGN, tmp_path / "campaigns" / "clavity")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    result = CliRunner().invoke(app, ["draft", "clavity", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "dry run: 3 model call(s) would be made" in result.output
```

Imports: `shutil`, `Path`, `CliRunner` from `typer.testing`, `app` from `promo.cli`, `LIMITS`/`HASHTAG_CAPS` from `promo.networks`, `finalize`/`prohibited_matches` from `promo.postprocess`, `load_brand_voice` from `promo.prompts`, `Intent`/`Network`/`load_manifest` from `promo.schema`. Annotate `tmp_path: Path`, `monkeypatch: pytest.MonkeyPatch`, `-> None` as the sibling tests do.

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/test_clavity_campaign.py -v`
Expected: FAIL; the first test raises `ManifestError` (no such file `campaigns/clavity/manifest.yaml`).

- [ ] **Step 4: Create `campaigns/clavity/manifest.yaml`** (licence header first, then exactly this data; it is the spec's fixed copy, so it is given in full):

```yaml
product:
  name: clavity
  tagline: Claude Code drives, a live Antigravity (agy) peer reviews.
  problem_statement: A review that agrees with the author instead of reading the code gives false confidence.
  key_features:
    - Claude Code and an Antigravity (agy) instance work in the same folder, one driving and one reviewing
    - Adversarial panel review of specs and plans, and a capstone review of committed code
    - Optional add-ons agy-autotrain, commonmemory and review-relay
  target_url: https://github.com/ckir/clavity
  audience: Claude Code users who already use the superpowers plugin
  proof_points:
    - Round 1 of an adversarial review of a snapshot change returned GREEN with zero findings, and it was wrong.
    - The setting AGY_INBOX_SNAPSHOT_KEEP fed tail -n +$((KEEP + 1)) in a bash script without validation.
    - bash evaluates a non-numeric name as 0, so abc, a negative number, or 0 all became tail -n +1, which lists every snapshot slot and deletes them all, including the snapshot written moments earlier by the same invocation.
    - "Measured with a control: KEEP=5 kept 4 slots; KEEP=0, abc and -1 kept 0, silently, with exit status 0."
    - The ledger's own reading is that a review whose findings never surprise the author has agreed with the author rather than read the code.
    - Fixed in commit 3adc045.
    - Source is clavity's own capstone ledger, the author's own account.
  prohibited_claims:
    - completely free
    - free for any use
    - catches every bug
    - no bugs
    - independently verified
    - guaranteed
    - production-ready
  disclosures:
    - "I'm the author of clavity."
brand_voice: campaigns/clavity/brand.md
confidential: false
launch_date: 2026-11-02
beats:
  - id: case-study
    offset_days: 0
    intent: deep-dive
    networks: [facebook]
    notes: Tell the snapshot-prune catch from the proof points in plain words for a developer who has never seen the project. Say it comes from clavity's own ledger, as my own account, one example and not a rate. Do not include any link or install command. Do not use hashtags.
  - id: install-comment
    offset_days: 0
    intent: custom
    networks: [facebook]
    notes: "Write the first comment under the case-study post, for Claude Code users. State that it needs the superpowers plugin (https://github.com/obra/superpowers) and Antigravity (agy), and that clavity is licensed PolyForm Noncommercial 1.0.0 for personal, academic and non-profit use only. Say clavity-dotnet and clavity-classic are mutually exclusive and give only the plugin route. Reproduce these two commands exactly, each on its own line: claude plugin marketplace add ckir/clavity and claude plugin install clavity@clavity. Include the repository link once."
  - id: addon-replies
    offset_days: 0
    intent: custom
    networks: [facebook]
    notes: "Write three short reply paragraphs for people who already installed the core plugin, one per add-on, each starting with its exact command: claude plugin install agy-autotrain@clavity (learns how to drive agy from everyday use), claude plugin install commonmemory@clavity (shared memory for Claude and agy), claude plugin install review-relay@clavity (assisted copy-paste review rounds with web AI models). No other claims."
```

- [ ] **Step 5: Create `campaigns/clavity/brand.md`**: voice prose in the register of the root `brand.md` (plain words, short sentences, dry humour, no hype, no exclamation marks, say what it did before why it matters; first person as the author), then the examples block with 1-2 lines. Each example line must be plain prose, contain no digits and no URL, avoid every prohibited phrase, and say it is the author's own project and one example. Example to start from: `A typo in one setting made a cleanup script delete every snapshot, including the one it had just written, and the first review round missed it. It is one example from my own project, not a rate.`

```
<!-- promo:examples:start -->
...your 1-2 lines...
<!-- promo:examples:end -->
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run pytest tests/test_clavity_campaign.py -v`
Expected: 8 passed. If `test_brand_examples_pass_post_processing` reports a warning, fix the example line; do not loosen the test.

- [ ] **Step 7: Run the repository gate**

Run: `just format && just check`
Expected: lint, typecheck, license and the whole suite pass (the prior suite had 252 tests; expect 260). If `just license` flags a new file, add the header from `header.txt` in the file's comment style.

- [ ] **Step 8: Commit**

```bash
git add campaigns/clavity tests/test_clavity_campaign.py
git commit -m "feat: add the clavity install campaign"
```

### Task 2: Generate, review and post (OWNER-RUN; the executor stops before the paid step)

**Files:** none modified. Output lands in `drafts/clavity/` (gitignored).

**Interfaces:**
- Consumes: Task 1's campaign `clavity`; `ANTHROPIC_API_KEY` in `.env` (README setup); the owner's browser and the target groups.
- Produces: three approved drafts, then the owner's hand posts and `promo posted` records.

- [ ] **Step 1 (executor): dry run**

Run: `uv run promo draft clavity --dry-run`
Expected: `dry run: 3 model call(s) would be made`, and no `drafts/` directory created.

- [ ] **Step 2 (owner): generate.** This makes 3 paid model calls with `claude-opus-5-5` (about 0.07 USD by the seam's 2026-10-24 list-price estimate of 0.024 USD per draft; not re-measured).

Run: `uv run promo draft clavity`
Expected: three drafts under `drafts/clavity/<beat>/facebook.md`, each status `draft`.

- [ ] **Step 3 (owner): review each draft** with `uv run promo review clavity`. Before approving a variant, apply the spec's pre-post checklist:
  1. Read the target group's self-promotion and link rules; post only where allowed.
  2. One post per group, never the same group twice.
  3. Paste the install commands from the README yourself; check Facebook keeps straight quotes.
  4. Re-check the README still says what the comment says.
  5. Compare every figure and claim with ledger lines 81-90 at clavity `7a6910e8`; approve no variant with an unexplained warning.
  6. The `case-study` draft has no link or install command; only `install-comment` carries the repository link.

- [ ] **Step 4 (owner): post by hand, then record.** Post the case study, add the install comment under it, keep the add-on replies for when someone asks.

Run: `uv run promo posted clavity/case-study/facebook --url <post url>`
Expected: the draft's status becomes `posted`. Repeat for `clavity/install-comment/facebook` with the comment's URL.

---

## Self-review (run 2026-10-26)

- **Spec coverage:** three beats, facebook only, offsets, intents (Task 1 Steps 2/4); proof_points and sources (Step 4, tests); disclosures and prohibited list (Global Constraints, `test_manifest_shape`); required wording for both beats (`test_required_wording_...`); comment-vs-body split (notes); `target_url` and UTM (target_url pinned; UTM is promo's own behaviour, unchanged); `confidential: false`; `launch_date` (Global Constraints); owner checklist items 1-6 (Task 2 Step 3); dry-run count 3 (Task 1 Step 6, Task 2 Step 1). Spec's "reply templates for add-ons" = `addon-replies`.
- **Gaps left, with where they resolve:** the `addon-replies` beat's required wording is only "no other claims" plus the exact commands (spec has no stricter text); draft quality and Facebook formatting (smart quotes, link ranking) are unverified and resolve at the owner's first post (Task 2). promo's duplicate-opening/similarity checks across the three drafts, whether `review` blocks approval on a warning, and `measured_length` for Facebook were not examined by the spec's panel; the first real run (Task 2 Step 2-3) reveals them.
- **Placeholders:** none. The only open body is the example line(s) in `brand.md`, whose constraints are stated and are enforced by a test.
- **Types:** names used by the tests match the Interfaces block (checked against the repo files 2026-10-26).
- **Proportion:** the plan is longer than the data it adds because the manifest is given verbatim; the tests carry the decisions.
