"""Interactive terminal review loop: choose, edit, regenerate, approve."""

import os
import re
import shlex
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

import pyperclip
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from promo import drafts
from promo.config import ConfigError, Profile, Settings
from promo.drafts import Draft, DraftError, Status
from promo.generate import regenerate_one
from promo.generators import GenerationError, Generator, make_generator
from promo.postprocess import prohibited_matches, tag_links, unsourced_numbers
from promo.schema import SLUG_RE, Manifest, ManifestError

_ESC_SEQ = re.compile(
    r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)"  # OSC
    r"|\x1b\[[0-?]*[ -/]*[@-~]"  # CSI
    r"|\x1b[@-Z\\-_]"  # other two-byte escapes
)
_CONTROL = re.compile(
    "[\x00-\x08\x0b-\x1f\x7f-\x9f\u200b-\u200f\u2028\u2029\u202a-\u202e\u2066-\u2069\ufeff]"
)


class ReviewIOError(Exception):
    """A terminal helper (such as the editor) could not be run."""


def sanitize(text: str) -> str:
    """Remove terminal control characters and escape sequences; keep \\n and \\t."""
    return _CONTROL.sub("", _ESC_SEQ.sub("", text))


class ReviewIO(Protocol):
    def read_key(self) -> str: ...
    def read_line(self, prompt: str) -> str: ...
    def print(self, renderable: Any) -> None: ...
    def copy(self, text: str) -> bool: ...
    def edit(self, path: Path) -> None: ...


class TerminalIO:
    def __init__(self) -> None:
        self._console = Console(highlight=False)

    def read_key(self) -> str:
        try:
            line = input("> ")
        except (EOFError, KeyboardInterrupt):
            return "q"
        return line.strip()[:1].lower() if line.strip() else ""

    def read_line(self, prompt: str) -> str:
        try:
            return input(prompt)
        except (EOFError, KeyboardInterrupt):
            return ""

    def print(self, renderable: Any) -> None:
        self._console.print(renderable)

    def copy(self, text: str) -> bool:
        try:
            pyperclip.copy(text)
        except pyperclip.PyperclipException:
            return False
        return True

    def edit(self, path: Path) -> None:
        editor = os.environ.get("EDITOR") or "vi"
        try:
            argv = shlex.split(editor)
            if not argv:
                argv = ["vi"]
            subprocess.run([*argv, str(path)], check=False)
        except (OSError, ValueError) as e:
            raise ReviewIOError(f"cannot run editor {editor!r}: {e}") from e


@dataclass
class ReviewSummary:
    approved: int = 0
    skipped: int = 0
    regenerated: int = 0


def select_for_review(drafts_root: Path, campaign: str, *, all_: bool) -> list[Path]:
    if not SLUG_RE.fullmatch(campaign):
        raise ManifestError(f"campaign name {campaign!r} must match [a-z0-9-]+")
    selected: list[Path] = []
    for path in sorted((drafts_root / campaign).glob("**/*.md")):
        try:
            meta = drafts.load(path).meta
        except DraftError:
            continue
        if all_:
            keep = meta.status in {Status.draft, Status.approved}
        else:
            keep = meta.status is Status.draft or (
                meta.status is Status.approved and bool(meta.warnings)
            )
        if keep:
            selected.append(path)
    return selected


def _error(io: ReviewIO, msg: str) -> None:
    io.print(Text(sanitize(msg), style="bold red"))


def _show(io: ReviewIO, draft: Draft, manifest: Manifest) -> None:
    meta = draft.meta
    chosen = str(meta.chosen) if meta.chosen is not None else "none"
    io.print(Text(sanitize(f"{meta.id}  status: {meta.status.value}  chosen: {chosen}")))
    for w in meta.warnings:
        io.print(Text(sanitize(f"warning: {w}"), style="red"))
    tagged = tag_links(
        manifest.product.target_url,
        manifest.product.target_url,
        meta.network,
        meta.campaign,
        meta.beat,
    )
    for n, text in enumerate(draft.variants, 1):
        if "prohibited_claim" in meta.warnings:
            hits = prohibited_matches(text, manifest.product.prohibited_claims)
            if hits:
                io.print(Text(sanitize(f"variant {n} matches: {', '.join(hits)}"), style="red"))
        if "unsourced_number" in meta.warnings:
            nums = unsourced_numbers(text, manifest, tagged)
            if nums:
                io.print(Text(sanitize(f"variant {n} unsourced: {', '.join(nums)}"), style="red"))
    if meta.needs_media and not meta.media:
        io.print(Text("this draft needs media: attach it with `promo media`", style="yellow"))
    for n, text in enumerate(draft.variants, 1):
        mark = " (chosen)" if meta.chosen == n else ""
        io.print(Panel(Text(sanitize(text)), title=Text(f"Variant {n}{mark}"), title_align="left"))
    io.print(Text("[1-9] choose  c copy  e edit  r regenerate  a approve  s skip  q quit"))


def review(
    drafts_root: Path,
    campaign: str,
    io: ReviewIO,
    *,
    all_: bool,
    manifest: Manifest,
    settings: Settings,
    now: datetime,
    generator_factory: Callable[[Profile, str | None], Generator] = make_generator,
) -> ReviewSummary:
    summary = ReviewSummary()
    for path in select_for_review(drafts_root, campaign, all_=all_):
        while True:
            draft: Draft | None
            try:
                draft = drafts.load(path)
            except DraftError as e:
                draft = None
                _error(io, str(e))
                io.print(Text("[e] edit  [s] skip  [q] quit"))
            if draft is not None:
                _show(io, draft, manifest)
            key = io.read_key()
            if key == "q":
                return summary
            if key == "s":
                summary.skipped += 1
                break
            if key == "e":
                try:
                    io.edit(path)
                except ReviewIOError as e:
                    _error(io, str(e))
                continue
            if draft is None:
                _error(io, "the draft is unreadable: only e, s and q are available")
                continue
            if len(key) == 1 and key in "123456789":
                n = int(key)
                if n > len(draft.variants):
                    _error(io, f"no variant {n}")
                    continue
                draft.meta.chosen = n
                try:
                    drafts.save(draft)
                except DraftError as e:
                    _error(io, str(e))
            elif key == "c":
                if draft.meta.chosen is None:
                    _error(io, "no variant has been chosen")
                    continue
                text = drafts.chosen_text(draft)
                if not io.copy(text):
                    io.print(Text("clipboard unavailable; text follows:"))
                    io.print(Text(sanitize(text)))
            elif key == "r":
                note = io.read_line("note: ")
                try:
                    regenerate_one(
                        path, manifest, settings, note, now, generator_factory=generator_factory
                    )
                except (GenerationError, ConfigError, DraftError, ManifestError) as e:
                    _error(io, str(e))
                    continue
                summary.regenerated += 1
            elif key == "a":
                try:
                    drafts.approve(path)
                except DraftError as e:
                    _error(io, str(e))
                    continue
                summary.approved += 1
                break
            else:
                _error(io, f"unknown key {key!r}")
    return summary
