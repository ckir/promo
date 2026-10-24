import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, NoReturn
from urllib.parse import urlsplit

import typer

from promo import __version__, drafts
from promo.config import ConfigError, Settings, load_settings, resolve_api_key
from promo.drafts import DraftError, draft_path
from promo.generate import run_draft
from promo.generators import (
    GenerationError,
    GenerationRequest,
    GenerationResult,
    Generator,
    make_generator,
)
from promo.review import TerminalIO, review
from promo.schema import SLUG_RE, Manifest, ManifestError, load_manifest

app = typer.Typer(no_args_is_help=True)

DRAFTS_ROOT = Path("drafts")
_EXPECTED = (DraftError, ConfigError, ManifestError, GenerationError)


def _fail(msg: str) -> NoReturn:
    typer.echo(msg, err=True)
    raise typer.Exit(1)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"promo {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show the version and exit.",
    ),
) -> None:
    """promo: draft-and-approve promo agent."""


class _NoModel:
    """Generator for dry runs: any call is a bug."""

    def generate(self, request: GenerationRequest) -> GenerationResult:
        raise GenerationError("dry run must not call the model")


def _existing_draft(draft_id: str) -> Path:
    try:
        path = draft_path(DRAFTS_ROOT, draft_id)
    except DraftError:
        _fail(f"no such draft: {draft_id}")
    if not path.is_file():
        _fail(f"no such draft: {draft_id}")
    return path


def _load_campaign(campaign: str) -> tuple[Settings, Manifest]:
    settings = load_settings()
    if not SLUG_RE.fullmatch(campaign):
        raise ManifestError(f"campaign name {campaign!r} must match [a-z0-9-]+")
    return settings, load_manifest(Path("campaigns") / campaign / "manifest.yaml")


@app.command()
def draft(
    campaign: str = typer.Argument(..., help="Campaign name (directory under campaigns/)."),
    beat: str | None = typer.Option(None, "--beat", help="Only this beat id."),
    network: str | None = typer.Option(None, "--network", help="Only this network."),
    force: bool = typer.Option(False, "--force", help="Regenerate existing drafts."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Plan only; make no model calls."),
    profile_name: str | None = typer.Option(None, "--profile", help="Generator profile."),
) -> None:
    """Generate drafts for a campaign."""
    try:
        settings, manifest = _load_campaign(campaign)
        profile = settings.profile(profile_name)
        generator: Generator
        if dry_run:
            generator = _NoModel()
        else:
            generator = make_generator(profile, resolve_api_key(profile))
        report = run_draft(
            manifest,
            campaign,
            settings,
            profile_name,
            generator,
            DRAFTS_ROOT,
            beat=beat,
            network=network,
            force=force,
            dry_run=dry_run,
            now=datetime.now(UTC),
        )
    except _EXPECTED as e:
        _fail(str(e))
    for did in report.generated:
        typer.echo(f"generated {did}")
        for warning in report.warnings.get(did, []):
            typer.echo(f"  warning: {warning}")
    for did in report.skipped:
        typer.echo(f"skipped {did}")
    if dry_run:
        typer.echo(f"dry run: {report.calls} model call(s) would be made")
    else:
        typer.echo(f"{report.calls} model call(s)")


@app.command()
def posted(
    draft_id: str = typer.Argument(..., help="Draft id: campaign/beat/network."),
    url: str = typer.Option(..., "--url", help="URL of the published post."),
    text_file: Annotated[
        Path | None, typer.Option("--text-file", help="File with the posted text.")
    ] = None,
) -> None:
    """Record that an approved draft was published."""
    url = url.strip()
    if any(ch.isspace() or ord(ch) < 32 or ord(ch) == 127 for ch in url):
        _fail("--url must be an http(s) URL without whitespace or control characters")
    try:
        parts = urlsplit(url)
    except ValueError:
        _fail("--url must be an http(s) URL")
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        _fail("--url must be an http(s) URL")
    path = _existing_draft(draft_id)
    text: str | None = None
    if text_file is not None:
        try:
            text = text_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            _fail(f"cannot read --text-file {text_file}: {e}")
    try:
        drafts.mark_posted(path, url, text, datetime.now(UTC))
    except _EXPECTED as e:
        _fail(str(e))
    typer.echo(f"posted {draft_id}")


@app.command()
def unapprove(
    draft_id: str = typer.Argument(..., help="Draft id: campaign/beat/network."),
) -> None:
    """Return an approved draft to draft status."""
    path = _existing_draft(draft_id)
    try:
        drafts.unapprove(path)
    except _EXPECTED as e:
        _fail(str(e))
    typer.echo(f"unapproved {draft_id}")


@app.command()
def media(
    draft_id: Annotated[str, typer.Argument(help="Draft id: campaign/beat/network.")],
    paths: Annotated[list[Path], typer.Argument(help="Media files to attach.")],
) -> None:
    """Attach media files to a draft."""
    path = _existing_draft(draft_id)
    try:
        drafts.add_media(path, paths)
    except _EXPECTED as e:
        _fail(str(e))
    typer.echo(f"media {draft_id}: {len(paths)} file(s)")


@app.command(name="review")
def review_cmd(
    campaign: Annotated[str, typer.Argument(help="Campaign name.")],
    all_: Annotated[bool, typer.Option("--all", help="Include approved drafts too.")] = False,
) -> None:
    """Review drafts interactively: choose, edit, regenerate, approve."""
    if not sys.stdin.isatty():
        _fail("promo review needs an interactive terminal")
    try:
        settings, manifest = _load_campaign(campaign)
        summary = review(
            DRAFTS_ROOT,
            campaign,
            TerminalIO(),
            all_=all_,
            manifest=manifest,
            settings=settings,
            now=datetime.now(UTC),
            generator_factory=make_generator,
        )
    except _EXPECTED as e:
        _fail(str(e))
    typer.echo(
        f"approved {summary.approved}, skipped {summary.skipped}, regenerated {summary.regenerated}"
    )
