# promo

A Python CLI studio for a draft-and-approve promo agent.
It generates social-post drafts from a campaign manifest using the Anthropic SDK.
Drafts are reviewed and approved by the owner on the command line.
Milestone 1 has no publishing and no social network credentials.

## What it is

`promo` reads a campaign manifest, asks a model for several variants of each post (one draft per beat and network), and stores them as markdown files. You review the variants in a terminal, pick one, edit it if needed, and approve it.

Milestone 1 cannot publish. It holds no social-network credentials. After you post by hand, `promo posted` records the URL you give it; it does not contact any network.

## Setup

    just setup                 # install dependencies (uv sync)
    cp .env.example .env       # then set ANTHROPIC_API_KEY in .env

`.env` and `drafts/` are gitignored. `--dry-run` needs no API key.

## Commands

Generate drafts without any model call, to see how many calls would be made:

    $ uv run promo draft example --dry-run
    dry run: 4 model call(s) would be made

Generate drafts (needs `ANTHROPIC_API_KEY`). Existing drafts are skipped unless you pass `--force`. `--beat`, `--network` and `--profile` narrow or change the run. `--force` regenerates and overwrites existing drafts, including approved ones, and clears `chosen` (attached media is kept). "Skipped" drafts are those that already exist, are posted, or are unreadable:

    uv run promo draft example

Review drafts one at a time (interactive terminal only). Keys: 1-9 choose a variant, `c` copy, `e` edit, `r` regenerate with a note, `a` approve, `s` skip, `q` quit. `--all` includes drafts that are already approved:

    uv run promo review example

After you have posted an approved draft by hand, record where it went. `--text-file` optionally records the text as posted:

    uv run promo posted example/launch/x --url https://x.com/...

Return an approved draft to draft status (a posted draft cannot be unapproved):

    uv run promo unapprove example/launch/x

Attach media files to a draft:

    uv run promo media example/launch/x PATH

## Draft ids and files

A draft id is `<campaign>/<beat>/<network>`, for example `example/launch/x`. Its file is `drafts/<campaign>/<beat>/<network>.md`: markdown with YAML front-matter (id, status, chosen variant, model, token usage, media, posted URL) followed by `## Variant N` sections. Status flows draft -> approved -> posted.

## Configuration

`promo.toml` in the working directory:

- `variants_per_draft`: variants generated per draft (1 to 9; 3 in the shipped file).
- `timezone`: IANA zone name. Defaults to the machine zone, or UTC if it cannot be resolved.
- `[generator] default`: the profile used when `--profile` is not given (`claude`).
- `[profiles.<name>]`: `kind`, `model`, `api_key_env`, `effort`, `max_tokens`, `trains_on_input`. The shipped `claude` profile is `kind = "anthropic"`, `model = "claude-opus-5-5"`, `effort = "high"`, `max_tokens = 4096`, key read from `ANTHROPIC_API_KEY`.
- `[networks.<name>]`: per-network overrides, `limit` (character limit) and `hashtag_cap`. The shipped file sets `[networks.x] limit = 280`.

## Campaign manifest

`campaigns/<campaign>/manifest.yaml` describes the product, the beats (id, day offset from `launch_date`, intent, networks) and the brand voice file. See `campaigns/example/manifest.yaml`; its `brand_voice: brand.md` points at `brand.md` in the repository root (the path is relative to where you run `promo`).

## The trains_on_input rule

A generator profile with `trains_on_input = true` is refused for a campaign whose manifest has `confidential: true`, which is the default. Set `confidential: false` in the manifest to allow it. Only the Anthropic profile exists in milestone 1.

## Development

    just check

runs `ruff check`, `ruff format --check`, `mypy src` and `pytest`. The publisher interface in `src/promo/publishers/` is a protocol only; nothing implements it yet.

Design spec: [docs/superpowers/specs/2026-10-24-promo-agent-design.md](docs/superpowers/specs/2026-10-24-promo-agent-design.md).

## Milestone status

- Milestone 1 (this): manifest, draft generation with the Anthropic SDK, terminal review, manual `posted` / `unapprove` / `media`.
- Not implemented: OpenAI-compatible generator, publishing and queue, assets, metrics.
