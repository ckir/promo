# clavity install campaign - design (short)

Status: APPROVED by the owner 2026-10-26 (agy escalation waived by the owner). Implemented on branch clavity-campaign.
Date: 2026-10-26. Size: small (one manifest, three drafts, one post per group).

## Intent and why
Get Claude Code users to install the clavity plugins, starting with the core `clavity@clavity`.
Channel and constraints are the owner's: a Facebook PERSONAL account, posting BY HAND into developer
groups. promo is at Milestone 1 (drafts only, no publishing), which fits: promo drafts, the owner edits,
approves and posts, then records the URL with `promo posted`.

## Goals
- A developer who reads the post understands one concrete thing clavity caught, and what clavity is.
- A reader who wants it can install it with no surprise prerequisite and no licence surprise.
- The owner can post in under 15 minutes per group.

## Non-goals
- Posting a multi-post series into the same group. Publishing via API. Promoting clavity-classic
  (a Windows .exe, not a `claude plugin` install). Any install-count claim.

## Anti-goals (failure even if it "works")
- A post that reads as an ad and gets the owner removed from a group.
- Anyone installing it, hitting a missing prerequisite (superpowers, Antigravity), and bouncing.
- Anyone reading "free" and using it for paid work: the licence is PolyForm Noncommercial 1.0.0.
- Presenting clavity's own ledger as an independent audit.

## Decisions (owner's)
- Goal = installs. Channel = developer Facebook groups, personal account, by hand.
- Shape = a single case-study post per group, install commands in the first comment.
- Case study = the AT-2 snapshot-prune catch (ledger lines 81-90, verified by the driver 2026-10-26).

## Approaches considered
1. Case-study post, install in first comment - CHOSEN by owner. Recommended by agy and, after
   verification, by the driver.
2. Install ladder, 3-4 posts - the driver's original lean; rejected: ranked group feeds break the
   sequence and repeat promotion risks moderation (agy's reasoning; unmeasured).
3. Demo-led with media - not chosen: needs media the owner would have to produce.
agy-first verdict: NEGOTIATE on the ladder, resolved by the driver conceding it (same record:
.clavity/seams/clavity-campaign.md, local only).

## The campaign (three beats, all `facebook`, all `offset_days: 0`)
`campaigns/clavity/manifest.yaml` with `brand_voice: campaigns/clavity/brand.md` (a new file, not the
root `brand.md`, which is Lumen Notes' voice; the path is relative to where `promo` is run).
`product.target_url` = `https://ckir.github.io/clavity/`, clavity's own site, which the owner wants promoted
(corrected 2026-10-26: the first version used the GitHub repo URL, taken from the README's marketplace name
without checking for a site). The live page was fetched 2026-10-26 (HTTP 200) and is identical to
`site/index.html` in the clavity repo; it carries the install commands with copy buttons, the prerequisites,
the licence and the user guide. promo appends UTM parameters to every occurrence of that URL, so the
comment's link will carry them. The site has no analytics (no analytics script in `site/index.html` or
`site/script.js`), so nothing reads those parameters; delete them by hand if you prefer a clean link.

| beat id | intent | becomes | content |
|---|---|---|---|
| `case-study` | deep-dive | the post body | the AT-2 catch, no links, no install command |
| `install-comment` | custom (notes required) | the FIRST COMMENT | install commands, prerequisites, licence line, repo link |
| `addon-replies` | custom (notes required) | reply text pasted on request | one short paragraph each for agy-autotrain, commonmemory, review-relay; the commonmemory paragraph must say it needs the npm package `@agentmemory/agentmemory` first (README line 30) |

The comment-vs-body split is a hypothesis from agy (links in the body may be penalised, code formatting
may break). Both are UNVERIFIED. The split costs little, so it stays; the owner can merge the two drafts
by hand if a group's rules prefer one post.

### Facts the drafts may use (these become `proof_points`; promo's `unsourced_number` check warns on any number in a draft that appears nowhere in the manifest text)
All from `/home/user/Development/Rust/clavity/docs/agy-capstone-ledger.md` lines 81-90, at clavity
commit `7a6910e8` (line numbers shift if the ledger changes; re-check before posting). The shell
behaviour was re-measured by the driver on 2026-10-26: with five items, `KEEP=5` deletes none, while
`KEEP=0`, `abc` and `-1` each list all five for deletion.
- Round 1 of a review returned GREEN with zero findings, and was wrong.
- `AGY_INBOX_SNAPSHOT_KEEP` fed `tail -n +$((KEEP + 1))` unvalidated.
- bash evaluates a non-numeric name as 0, so `abc`, a negative, or `0` made it `tail -n +1`, which lists
  every slot and deletes them all, including the snapshot written moments earlier by the same invocation.
- Measured with a control: KEEP=5 kept 4 slots; KEEP=0, abc and -1 kept 0, silently, exit 0.
- The ledger's reading: a review whose findings never surprise the author has agreed with the author.
- Fixed in commit `3adc045`.
Install and prerequisite facts: `/home/user/Development/Rust/clavity/README.md` lines 15, 47, 64-74, 104.

### Required wording (enforced where promo can, else by the owner's pre-post checklist)
- `disclosures`: "I'm the author of clavity." promo appends it to every draft if missing.
- `prohibited_claims`: promo flags a draft whose text CONTAINS any phrase, case-insensitive, with no
  negation handling (`prohibited_matches` in `src/promo/postprocess.py`: `p.lower() in lowered`). So a
  phrase may not be one the required wording itself needs ("not an independent audit" would trip
  "independent audit"). Use phrases a truthful draft never needs: "completely free", "free for any use",
  "catches every bug", "no bugs", "independently verified", "guaranteed", "production-ready".
- The install comment must state: Claude Code users only; requires the superpowers plugin and
  Antigravity (agy); licence is PolyForm Noncommercial 1.0.0, for personal, academic and non-profit
  use only; clavity-dotnet and clavity-classic are mutually exclusive, and the comment gives only the
  `claude plugin` route.
- The post must say the catch comes from clavity's own ledger, as the author's own account, one example
  and not a rate. Word it without the prohibited phrases above.

## Owner-visible signals
Comments asking setup questions. Installs themselves are NOT visible, and that signal is not verified to
predict them. The site has no analytics, and the repo's GitHub traffic page probably does not count visits to
the Pages site (UNVERIFIED), so site visits are not visible unless the owner adds analytics.

## Owner's pre-post checklist (promo cannot do these)
1. Read each target group's rules on self-promotion and links BEFORE posting; post only where allowed.
2. One post per group, never the same group twice; do not post to many groups in one day (UNVERIFIED
   whether that matters; cheap to follow).
3. Paste the install commands from README.md verbatim, as promo cannot check shell commands. Check
   that straight quotes survive Facebook (agy's smart-quote hypothesis is UNVERIFIED).
4. Confirm the README still says what the comment says before each post (the README can change).
5. promo's checks only WARN (they are not proof). Compare every figure and claim in the variant you
   pick with the ledger lines above. Do not approve a variant with an unexplained warning.
6. The `case-study` draft must contain no link and no install command; the `install-comment` draft is
   the only one that carries `target_url`. promo cannot enforce this per beat (`prohibited_claims`
   is product-wide), so check it by eye. Ask `install-comment`'s notes to reproduce the README
   commands exactly, and still paste them yourself from the README.

## Left to the builder
- Write `campaigns/clavity/manifest.yaml` and `campaigns/clavity/brand.md` (voice: plain, dry, no
  hype, matching root `brand.md`; examples block with 1-2 sample lines from the facts above).
- `launch_date` is required by the schema and has no meaning for a one-shot post: my call is the
  intended posting date; the owner changes it freely.
- `confidential: false` is my call (the repo is public). `confidential: true` only refuses generator
  profiles with `trains_on_input = true`, and only the Anthropic profile exists, so it changes nothing today.
- Run `uv run promo draft clavity --dry-run` (expects 3 model calls), then the real run, then review.
- `just check` must stay green; adding a campaign must not change source code.

## Self-audit (exhaustiveness)
Closed in this doc: the three-beat shape; which facts feed `unsourced_number`; disclosure and
prohibited-claim lists; prerequisites and licence wording; checklist for what promo cannot enforce.
Remaining, with where each resolves:
- Exact `brand.md` wording and the draft text: resolved at implementation, by the owner's review.
- Which groups and their rules: only the owner can; not resolvable in this doc.
- Whether the body/comment split and the smart-quote concern are real: UNVERIFIED, resolved by the
  owner trying one post; the doc does not depend on them.
- Number check: `_NUMBER = \d[\d.,]*` splits `3adc045` into `3` and `045` and reads `-1` as `1`; each is
  sourced if it appears in the manifest text. Put the sha and figures in `proof_points` verbatim.
  Confirmed by reading `postprocess.py`; the first real run will show it in practice.
- No metric ties posts to installs; stated, not solved.
- Not examined by the panel: promo's duplicate-opening and similarity checks across the three drafts,
  whether `review` blocks approval on a warning, and `measured_length` for Facebook. Resolved by the
  first dry run and review (plan level).

## Stand-downs
None yet. Panel round 1 (solo, driver only; agy escalation pending the owner's decision) raised and
FOLDED: (1) required wording contradicted `prohibited_claims` (substring match, no negation);
(2) `brand_voice` and `confidential` wording was garbled; (3) `target_url` and UTM behaviour was missing;
(4) ledger line numbers were unpinned; (5) per-beat "no link in the post" had no enforcer, so it moved
to the owner's checklist.
