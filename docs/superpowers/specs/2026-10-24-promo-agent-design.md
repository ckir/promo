# promo: a draft-and-approve agent for promoting products on social media

Date: 2026-10-24
Status: reviewed (builder check + six-round adversarial panel, GREEN), awaiting owner approval
Authors: Claude (driver) with agy (peer). Design and scaffold were negotiated over four consult
rounds; the finished document went through a builder check and a six-round adversarial panel,
the last two rounds covering items adopted from a second independent design (records in
`.clavity/seams/`, local and gitignored).

## 1. Intent

A solo developer wants a tool that turns a product into social-media promotion with as little
blank-page work as possible, without handing an LLM the keys to live accounts. The agent drafts;
a human approves; publishing, when it exists at all, happens only through official channels and
only after an explicit confirmation.

The reason for the shape: the content side is where an LLM earns its keep (platform-native copy,
hook variants, hashtags, image prompts, calendars). The publishing side is gated by platform
rules, app reviews and per-post pricing that no amount of code removes, and unsupervised posting
is how accounts get suspended and brands embarrassed.

## 2. Goals, non-goals, anti-goals

Goals
- From one product description, produce ready-to-review copy for several networks in minutes.
- Keep a human approval step between generation and anything public.
- Record what was actually published so later milestones can learn from it.
- Stay runnable by one person on one laptop with no hosted services.

Non-goals (may come later, not designed here)
- Chat-card approval surfaces (Slack, Discord, Telegram).
- Fully autonomous posting on a schedule.
- Video generation.

Anti-goals (a build that does these has failed even if it works)
- Browser automation of social sites. Ban risk.
- Automated replies to comments, mass likes, follows or DMs.
- Identical text blasted to every network at the same moment.
- Relying on the prompt to remember disclosures such as `#ad`.
- Any path by which saving a file publishes something.
- Paid advertising: creating, activating or funding ads. Never in this project.

## 3. Facts the design rests on (verified 2026-10-24)

| Fact | Consequence |
|---|---|
| X API is pay-per-use since Feb 2026; free tier closed to new developers; posts containing a URL are priced far above plain posts; no native scheduling outside the Ads API. | X publishing is a deliberate cost decision; the agent runs its own queue. |
| Instagram publishing API covers professional accounts only; Facebook has not allowed API posting to personal profiles since 2018; Meta app review is required for production. | Meta adapters assume professional or Page accounts. |
| TikTok direct post works for unaudited apps, but every post is forced private until the app passes audit. | TikTok is "private-only until audited" in the policy table. |
| Buffer launched a new GraphQL public API in 2026; Ayrshare starts at 149 USD/month; self-hosted Postiz and Mixpost exist. | Aggregators are a milestone-2 option, not a dependency. |
| anthropic Python SDK is on a 2.x major (2.2.0, 2026-10-23), requires Python 3.10+. | Pin `>=2.2`; read the 2.x changelog before writing any call. |
| Host: Python 3.14.4, uv 0.12.21, just, gh, xsel and wl-copy present. | uv manages a 3.12 interpreter; clipboard works locally. |

Sources are listed in section 12.

## 4. Approaches considered

1. Fully autonomous poster. Repo event, LLM generates, direct publish. Rejected: hallucinated
   claims and brand missteps go live with nobody looking, and every network's rate and policy
   limits become production incidents.
2. Analytics-only observer. Reads metrics, suggests strategy. Rejected as the primary shape:
   solves half the workflow and needs published posts to exist first.
3. Draft-and-approve content studio. Chosen. Both reviewers recommended it independently.
   Within it, two sub-forks were negotiated:
   - Approval surface: chat cards with buttons (agy's first proposal) versus a local review
     loop (Claude's). Chosen: an interactive terminal loop. Chat cards cost a bot
     integration, webhooks and hosting before the first post.
   - Sequencing: publishing adapter in the core loop from day one (agy) versus no publishing
     integration in milestone one (Claude). Chosen: none in milestone one. Copy quality is
     validated in days, before any app review, OAuth or per-post spend.

## 5. Primary object: the campaign

The unit of work is a campaign, not a single post. A product launch is a sequence of beats
(teaser, launch, deep-dive, social proof) across networks; isolated per-network posts produce
repetitive announcements. A one-beat campaign is the degenerate single-post case and nothing
forces more.

`campaigns/<name>/manifest.yaml`:

```yaml
product:
  name: string
  tagline: string
  problem_statement: string
  key_features: [string]
  target_url: string
  audience: string
  proof_points: [string]       # real quotes, numbers, testimonials; may be empty
  prohibited_claims: [string]  # phrases that must never appear, e.g. "guaranteed"; may be empty
  disclosures: [string]        # injected verbatim by code, e.g. "#ad"
brand_voice: brand.md           # path, relative to repo root
confidential: true              # default; false permits generator profiles that train on input
launch_date: 2026-11-03         # ISO date; beat offsets are relative to it
beats:
  - id: teaser                  # slug [a-z0-9-]+, unique within the campaign
    offset_days: -2
    intent: teaser | launch | deep-dive | social-proof | custom
    networks: [x, linkedin, threads, mastodon, bluesky, instagram, facebook, tiktok, pinterest]
    notes: string               # optional steer for this beat; required when intent is custom
```

Validation is strict: unknown fields fail, every listed field is required except `notes`,
`beats[].id` values are unique, a manifest with zero beats is rejected, and a beat with intent
`social-proof` is rejected when `proof_points` is empty. The campaign name is the directory
name and must match the same slug rule, so a draft id `<campaign>/<beat>/<network>` is
unambiguous and safe as a path and as a CLI argument.

Grounding rule: the generator may state only facts present in the manifest. The prompt says so,
and code checks it: any number in a variant that does not appear in the manifest adds
`unsourced_number` to the draft's `warnings`. This is the mechanism behind the "no hallucinated
claims" rejection of approach 1 in section 4.

`brand.md` has two parts: free prose describing the voice, and a machine-owned block between
`<!-- promo:examples:start -->` and `<!-- promo:examples:end -->` holding the few-shot
examples. Milestone 1 reads the block; milestone 4 rewrites only the block.

## 6. Milestones

### Milestone 1: CLI studio, nothing can post

Commands:

- `promo draft <campaign>`: for each beat and network, make one structured-output call
  through the `Generator` interface (milestone 1 ships the Anthropic implementation, which
  uses `messages.parse` against a pydantic `Variants` model, and an in-process fake used by
  the tests) with the manifest, the brand voice few-shots and the per-network rules, and write
  `drafts/<campaign>/<beat>/<network>.md`. Front-matter holds `id`, `campaign`, `beat`,
  `network`, `status` (draft, approved, scheduled, posted), `variants` (count), `chosen`
  (index or null), `generated_at`, `model`, `usage` (input and output tokens, so spend is
  visible per draft), `needs_media` (true for Instagram, TikTok, Pinterest; such drafts are
  text only and cannot be scheduled or published until `media` is non-empty), `media` (list
  of file paths, empty by default), and `warnings` (list, see post-processing). The body holds the variants under stable headings
  `## Variant 1` .. `## Variant N`; `chosen` is validated against the headings present after
  every edit, never trusted blindly.
  Idempotency: an existing draft file is left alone on re-run, so a run that fails on beat 3
  of 5 resumes without re-spending on beats 1 and 2. `--force` regenerates files in `draft`
  or `approved` status; a `posted` draft is never regenerated by any flag, since it holds the
  record of what went live. `--beat <id>` and `--network <name>` limit a run; `--dry-run`
  prints the number of API calls a run would make and exits.
- `promo review <campaign>`: interactive terminal loop over drafts in `draft` status plus
  any `approved` draft that carries a warning (for example `queue_failed`), so nothing that
  needs a human's eyes is hidden; `--all` widens it to every draft that is not `scheduled` or
  `posted`. Shows the variants rendered with rich, with any `warnings` highlighted. Keys: `1`..`9` choose a
  variant, `c` copy the chosen variant to the clipboard, `e` open the file in `$EDITOR`
  (falls back to `vi` when unset), `r` regenerate all variants of this draft with a note
  (resets `chosen`), `a` approve, `s` skip, `q` quit. Refuses to start when stdin is not a terminal. Clipboard
  copy falls back to printing the text when no clipboard utility is available. After the
  editor returns, the file is re-read and re-validated before any status is written, so an
  edit in the editor and a status change in the loop never overwrite each other. `a` requires
  `chosen` to be set.
- `promo posted <draft-id> --url <url> [--text-file <path>]`: records `published_url`,
  `published_at` and `published_text` (defaults to the chosen variant; errors out when
  `chosen` is unset and no text file is given) into the draft's front-matter and sets
  `status: posted`. This closes the gap agy identified: once the owner
  pastes by hand and tweaks a hook in the network's editor, the local file and the live post
  diverge, and milestone 4 would have nothing true to read.
- `promo unapprove <draft-id>`: returns an `approved` draft to `draft` status, keeping its
  text and `chosen`, so a change of mind costs no regeneration. Refuses any other status.
- `promo media <draft-id> <path>...`: records existing files into the draft's `media` list
  (paths are validated to exist and be under the repository or an absolute path the owner
  names). This is how a draft for a visual-first network becomes publishable; milestone 3's
  renderer calls the same writer.

Deterministic post-processing, in code, after generation and before writing:

- per-network length limits (starting values: X 280 for non-premium, Threads 500, Bluesky
  300, Mastodon 500, LinkedIn 3000, Instagram caption 2200, Facebook 5000, TikTok caption
  2200, Pinterest description 500; the table lives in one module, is the oracle for its
  tests, and each value is re-checked against the network's docs when its adapter is written),
- hashtag caps per network,
- disclosure injection from the manifest,
- near-duplicate rejection across networks within a beat (same beat, two networks, text
  similarity above a threshold triggers regeneration of the later one, at most twice; after
  that the draft is written with `near_duplicate` in `warnings` and the review loop shows it),
- narrative-progression check across beats (two beats with the same intent must not share an
  opening sentence; same retry cap and `warnings` entry `repeats_beat`),
- prohibited-claims check: a case-insensitive match of any `prohibited_claims` phrase adds
  `prohibited_claim` to `warnings` and the review loop shows the offending phrase,
- link tagging: every occurrence of `target_url` in a variant is rewritten with
  `utm_source=<network>`, `utm_medium=social`, `utm_campaign=<campaign>` and
  `utm_content=<beat>` added to the query component (parsed and rebuilt with
  `urllib.parse`, so a fragment stays after the query, an existing query string is kept, and
  a `utm_*` key the owner already set is not overridden); the tagged URL counts as the
  manifest URL for the grounding check.

The checks run in a fixed order, and the order is part of the contract: disclosure
injection, then link tagging, then the length-limit check against the final text, then the
grounding, prohibited-claims, near-duplicate and narrative checks. Length is measured the way
the network measures it: X and Mastodon count any URL as a fixed 23 characters (starting
value, re-checked with the adapter), the others count the literal text.

Every post-processing check is a pure function over strings and the manifest, so the whole
layer is tested without the API.

Status machine: `draft` becomes `approved` only through `a` in the review loop. `approved`
becomes `posted` through `promo posted` (milestone 1, by hand) or through a successful
`promo publish` or queue run (milestone 2), all of which use the same writer to record
`published_url`, `published_at` and `published_text`. `approved` becomes `scheduled` only
through `promo schedule`; `scheduled` returns to `approved` through `promo queue cancel` or a
permanent queue failure (which also adds `queue_failed` to `warnings`), and becomes `posted`
when the queue run succeeds. Editing a file in `$EDITOR` never changes status. `approved`
returns to `draft` through `promo unapprove` (text kept) or `--force` (text regenerated,
`chosen` cleared); `--force` also applies to `draft` files and refuses `scheduled` and
`posted` files. `posted` is terminal. `publish`,
`schedule` and `posted` accept only a draft in `approved` status (which guarantees `chosen`
is set, since `a` requires it) and therefore refuse `draft`, `scheduled` and `posted` files.
`promo media` refuses `scheduled` and `posted` files, so the queue snapshot and the file
cannot drift apart.

Storage in milestone 1 is the draft file itself. There is no database.

Configuration: secrets come from `.env`; `promo.toml` holds `variants_per_draft` (default
3), `timezone` (an IANA name, default the machine's local zone), per-network overrides such
as the X character limit for a premium account, and generator profiles:

```toml
[generator]
default = "claude"

[profiles.claude]
kind = "anthropic"            # anthropic | openai-compatible (the latter from milestone 1b)
model = "claude-opus-5-5"
api_key_env = "ANTHROPIC_API_KEY"
effort = "high"
max_tokens = 4096
trains_on_input = false
```

`promo draft --profile <name>` overrides the default for one run. Every draft records the
profile name and model in front-matter next to `usage`, so drafts from different models are
distinguishable later, and `r` in the review loop regenerates with the profile recorded on
the draft, not the configured default. `api_key_env` is optional, since local endpoints
need no key; `effort` is honoured only by the Anthropic kind and ignored elsewhere. A profile with `trains_on_input = true` is refused before the first
call unless the campaign manifest sets `confidential: false` (the manifest field defaults to
`true`); the flag belongs to the configured profile, not the vendor, because the same
vendor's terms differ by tier and by region.

Nothing in milestone 1 has credentials for, or code paths to, any social network.

### Milestone 1b: a second generator

Adds one `openai-compatible` generator configured by `base_url`, `model` and `api_key_env`.
One implementation covers Ollama, LM Studio, OpenRouter, Groq and Gemini's compatible
endpoint. It requests schema-constrained output (`response_format` of type `json_schema`)
and, when the endpoint rejects or ignores that, falls back to JSON mode with the schema in
the prompt, pydantic validation and two retries; a draft produced by the fallback carries
`schema_fallback` in `warnings`, and a draft that still fails validation is not written and
the run reports it. Rate-limit and model-not-found responses stop the run with the
provider's message; nothing is retried silently across a daily quota. The post-processing
checks are unchanged and are the quality floor for weaker models.

Why staged, and why at all: at roughly one cent per campaign on the cheapest Claude model,
price is not the reason. The reasons are offline use and privacy with a local model, and
vendor independence. Milestone 1 is judged on a strong model so that weak copy can be
attributed to the prompt or the checks rather than the model; the fake generator in
milestone 1 proves the interface does not carry Anthropic-specific shapes. Facts measured on
2026-10-24 that a builder should expect: this machine has no GPU, so a local model runs on
CPU at an unmeasured speed; OpenRouter's free tier allows 50 requests a day, which one
20-draft campaign with retries can exceed; nine of its nineteen free models route to hosts
that may train on prompts; Gemini's unpaid tier trains on input except for EEA, Swiss and UK
users. The `trains_on_input` flag exists for exactly this.

### Milestone 2: one publisher

- A `Publisher` protocol: `publish(draft) -> (remote_id, url)` and
  `fetch_metrics(remote_id) -> Metrics`.
- The first concrete adapter is chosen by the owner's actual accounts, not by this document.
  The policy facts in section 3 are encoded next to the adapter registry so an unsupported
  account type fails at configuration time, not at publish time.
- `promo publish <draft-id>`: prints the exact text, the network, the account and, for X,
  a reminder that a post with a URL is billed at the higher rate, asks `y/N`, then publishes
  and, on success, records the result and sets `status: posted` exactly as `promo posted`
  does. It requires a terminal; there is no `--yes` flag, so it cannot be driven by a pipe.
  No background watcher. No publish on status change. Ever.
- `promo schedule <draft-id> --at <datetime>`: the same print-and-confirm as `publish`, but
  on `y` the exact confirmed text and the `media` paths are copied into the queue row as an
  immutable snapshot, and the draft's status becomes `scheduled`. `--at` takes an ISO 8601
  datetime; one without an offset is interpreted in the `timezone` named in `promo.toml`
  (an IANA name, resolved with the standard library's zoneinfo, so daylight-saving
  transitions are handled), and the confirmation prints both the local and the UTC time.
  Queue rows store UTC. The confirmation happens
  here, once, by a human at a terminal; nothing enters the queue any other way.
- A SQLite file (`promo.db`, gitignored) holds the queue. `promo queue run` publishes only
  rows that were explicitly scheduled and are now due, and it publishes the snapshot in the
  row; it never re-reads the draft body, so no later edit or regeneration can change what
  goes out. Transient errors get exponential backoff; after a bounded number of attempts the
  row is marked failed and the draft returns to `approved` with a `queue_failed` warning. On
  success the draft is marked `posted` through the shared writer. The command is invoked by
  the owner or by an OS scheduler (cron, systemd timer, GitHub Action); it is not a daemon.
  `promo queue list` and `promo queue cancel <draft-id>` complete the set.
- At-most-once publishing. A queue run first takes an OS advisory lock (`fcntl.flock` on a
  lock file next to `promo.db`); the kernel releases it when the process dies, so a crash
  never leaves a stale lock, and a second run that finds it held exits at once. The mere
  existence of the file means nothing; only the held lock does. Each due row is then claimed in
  a single `BEGIN IMMEDIATE` transaction that stamps `claimed_at` before any network call, so
  two runs can never pick the same row. A row whose claim is older than the configured lease
  and that is neither posted nor failed is never retried automatically: it is marked
  `unknown` (the process may have died after the network accepted the post but before the
  result was written), `queue list` shows it first, and the owner resolves it by checking
  the account and running `promo queue resolve`. The result write order on success is:
  queue row, then front-matter; a crash between the two is detected on the next run by a
  posted row whose draft is still `scheduled`, and the front-matter write is replayed from
  the row. Duplicate posts are the failure this design refuses to risk; a missed post that a
  human has to resolve is the accepted price.
- `promo queue resolve <draft-id> --posted --url <url>` closes an `unknown` row as posted
  and marks the draft `posted` through the shared writer, recording the snapshot text as
  `published_text`. `promo queue resolve <draft-id> --not-posted` closes the row as failed
  and returns the draft to `approved` with a `queue_failed` warning, after which it can be
  scheduled again. `resolve` acts only on `unknown` rows; it is the one command that may move
  a `scheduled` draft by hand, and `promo posted` keeps its approved-only rule.
- `promo queue cancel` on a row that is currently claimed refuses and says so; cancellation
  is only possible for rows not yet claimed.
- A draft with `needs_media: true` and an empty `media` list is refused by `publish` and
  `schedule`.
- Where a network exposes its own disclosure control (Instagram branded content, LinkedIn
  sponsored flags), the adapter sets it from the manifest's `disclosures`; the text
  injection remains, since not every network has such a control.

### Milestone 3: assets (conditional)

Only if the owner's products come without visuals. An HTML template rendered to PNG with
Playwright, filled from manifest fields, and recorded on the draft through the same writer as
`promo media`. Visual-first networks (Instagram, TikTok, Pinterest) are text-only drafts until
this milestone exists or the owner supplies media. YouTube is not a target network in this
design; video is a non-goal.
Playwright is an optional extra (`promo[assets]`) so milestones 1 and 2 never install a browser.

### Milestone 4: the loop

- `promo metrics`: for posted drafts older than 24 hours, call `fetch_metrics` and store the
  result in SQLite with a timestamp and the source. A metric the network does not return is
  stored and shown as unavailable, never as zero, so a missing number cannot pull a post out
  of the top quartile.
- `promo refresh-voice`: weekly, the top-quartile posts by engagement are proposed as the
  few-shot block in `brand.md`; the owner reviews the diff before it is written.

Not in the loop: minute-level timing optimisation, automatic comment replies.

## 7. Repository scaffold and tooling

```
pyproject.toml          [project] promo, requires-python >=3.12, build-backend uv_build,
                        [project.scripts] promo = "promo.cli:app"
uv.lock
.python-version         3.12  (uv manages it; host 3.14 untouched)
justfile                setup | lint | typecheck | test | check (= lint + typecheck + test)
.github/workflows/ci.yml   uv sync --frozen; just check; matrix 3.12, 3.13
.env.example            ANTHROPIC_API_KEY=
promo.toml              generator profiles, variants_per_draft, timezone, network overrides
brand.md                voice description + few-shot examples (tracked)
campaigns/example/manifest.yaml
drafts/                 gitignored, anchored as /drafts/
*.db                    gitignored
.claude/recommended-tools.json   uv, just, xsel-or-wl-copy
src/promo/
  cli.py                typer app; one subcommand per command above
  config.py             tomllib + python-dotenv
  schema.py             pydantic v2 models: Manifest, Product, Beat, DraftFrontMatter, Variants
  generate.py           prompt assembly, calls a Generator, post-processes -> draft file
  generators/__init__.py   Generator protocol: generate(request) -> Variants + usage
  generators/anthropic.py  the Claude implementation (M1)
  generators/fake.py       deterministic in-process implementation for tests (M1)
  generators/openai_compat.py   base_url + model + key implementation (M1b)
  postprocess.py        pure functions; the network limits table
  review.py             rich rendering + key loop; pyperclip in try/except; isatty guard
  publishers/__init__.py   Publisher protocol only (M1); adapters land here in M2
  store.py              M2 (SQLite); absent in M1
  assets/               M3; optional extra
tests/                  pytest; generators/fake.py drives generate.py so the pipeline is
                        tested without network; clipboard and $EDITOR mocked; isatty tested
docs/superpowers/specs/ this document
```

Dependencies (current releases on 2026-10-24, all support a 3.12 floor): anthropic >=2.2,
typer, rich, pydantic >=2, python-frontmatter, PyYAML, python-dotenv, pyperclip. Dev group:
pytest, pytest-cov, ruff, mypy. Optional `assets`: playwright. Milestone 1b adds the
`openai` package, used only by the compatible generator against third-party endpoints.

Gates: ruff (lint and format, line length 100, rules E F I UP B); mypy with
`disallow_untyped_defs`, `check_untyped_defs`, `warn_unused_ignores`, and one
`ignore_missing_imports` override for `pyperclip.*` (the only dependency without a `py.typed`
marker, measured); pytest. `just check` runs all three locally; CI runs the same command.

Deliberately not used: pre-commit (one developer, one command, already the CI gate), poetry
or pipenv (uv covers them), textual (a full TUI is over-build for a per-draft loop), agent
frameworks (one structured call per draft, no agent loop), Docker (local CLI), a daemon.

## 8. Constraints

- Generation on a model other than Claude is a milestone-1b feature behind the same
  interface; the Claude code path uses the Anthropic SDK and never an OpenAI-compatible
  shim, and the compatible adapter never carries Anthropic-specific request shapes.

- Public GitHub repository. Nothing confidential may be tracked: drafts, databases, env files
  stay ignored; `.env.example` is tracked.
- One developer, one machine. No hosted components in milestones 1 and 2.
- Platform access is the schedule's critical path, not code. App reviews take weeks; the
  first publisher is chosen by what the owner already holds.
- Every quantitative platform fact in this document is a snapshot. Adapters re-verify the
  rule they depend on against the platform's docs when they are written.

## 9. Decisions made during the conversation, in the owner's words where given

- Shape: draft-and-approve. (Both reviewers; owner asked for a common agreed design.)
- Review surface: terminal loop, not chat cards. (Negotiated; agy conceded.)
- Milestone 1 has no publishing integration. (Negotiated; agy conceded.)
- Campaign is the primary object. (agy proposed; Claude accepted.)
- Front-matter is the milestone-1 store; SQLite arrives with the queue. (agy proposed;
  Claude accepted.)
- No pre-commit; targeted mypy. (agy proposed; Claude accepted after measurement.)
- Adopted from a second, independently produced design the owner shared
  (`socialmediaagent/docs`, a hosted multi-tenant variant of the same idea): prohibited
  claims, UTM link tagging, `promo unapprove`, unavailable-not-zero metrics, explicit
  timezone handling, paid ads as an anti-goal. (Owner chose this list; the content-hash
  binding of approvals was considered and left out.)

## 10. Calls made by the author, open to override

- Python floor 3.12, tested on 3.12 and 3.13.
- Default model `claude-opus-5-5` with adaptive thinking; effort configurable. The owner
  can make the near-free `claude-haiku-5-5` the default profile with one config line.
- Provider support is staged: interface plus Anthropic and fake generators in milestone 1,
  the OpenAI-compatible generator and the `trains_on_input` guard in milestone 1b.
  (Negotiated with agy, who first proposed shipping the second generator in milestone 1.)
- Network length-limit table values in section 6 are starting values; the table is the single
  source and its tests pin it.
- Near-duplicate threshold and similarity measure are left to the builder, with the
  requirement that the check is a pure function with its own tests.
- Draft identifiers are `<campaign>/<beat>/<network>` slugs, stable across regeneration.
- One API call per draft (beat x network), not one per beat. A per-beat call would make the
  cross-network duplicate check cheaper, but it makes resumption, `r` in the review loop and
  the `--network` filter awkward, and a draft is the unit the owner reviews.
- `proof_points` is the only source for quotes and numbers; the grounding check flags any
  other number. This is a warning, not a hard failure, so the owner can accept a number the
  check could not match (a date, a percentage written in words).
- Milestone 2 publishing confirmation happens at `schedule` or `publish` time, never at
  queue-run time; a human at a terminal is the only entry into the queue.
- The queue is at-most-once, not exactly-once. SQLite and the draft files are two stores
  with no shared transaction, so the ambiguous window after a network call is resolved by a
  human, never by an automatic retry.

## 11. Left to the builder

- Prompt wording and the structure of the per-network rule block.
- Exact rich layout of the review screen.
- How variants are numbered in the markdown body (must round-trip through front-matter
  `chosen`).
- Similarity algorithm for the duplicate check.
- Which SQLite schema the milestone-2 queue uses.

## 12. Stand-downs

Findings raised in review and stood down, with the guard that makes each unreachable:

- DISCARDED-BELOW-FLOOR: prompt injection through manifest or brand voice text. Both files
  are authored by the owner and tracked in the owner's own repository (section 5, section 8);
  no third-party text enters a prompt in milestones 1 to 3. Milestone 4 feeds back only the
  owner's own published posts.
- DISCARDED-BELOW-FLOOR: driving `promo publish` through a pipe with `yes`. The command
  requires a terminal and has no `--yes` flag (section 6, milestone 2).

## 13. Sources

- X API pricing and tiers, 2026: https://www.wearefounders.uk/the-x-api-price-hike-a-blow-to-indie-hackers/ and https://www.upload-post.com/x-api-pricing/
- X has no native scheduling outside Ads: https://skedsocial.com/blog/schedule-x-twitter-posts.md
- Instagram publishing, professional accounts only: https://developers.facebook.com/docs/instagram-platform/content-publishing
- Facebook personal profiles closed to API publishing: https://help.planable.io/hc/en-us/articles/21715294125340
- TikTok direct post, private until audited: https://developers.tiktok.com/doc/content-posting-api-reference-direct-post
- Buffer API relaunch and legacy retirement: https://buffer.com/resources/legacy-rest-api-retired/
- Ayrshare pricing: https://www.ayrshare.com/pricing
- Package versions: PyPI JSON API, queried 2026-10-24.
