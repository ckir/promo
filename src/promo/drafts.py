"""Draft files: front-matter contract, variants and status transitions."""

import os
import re
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

import frontmatter
import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from promo.schema import Network

VARIANT_RE = re.compile(r"^## Variant (\d+)$", re.MULTILINE)


class DraftError(Exception):
    """A draft file is malformed or a status transition is not allowed."""


class Status(StrEnum):
    draft = "draft"
    approved = "approved"
    scheduled = "scheduled"
    posted = "posted"


class Usage(BaseModel):
    input_tokens: int
    output_tokens: int


class DraftMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    campaign: str
    beat: str
    network: Network
    status: Status
    variants: int
    chosen: int | None
    generated_at: datetime
    profile: str
    model: str
    usage: Usage
    needs_media: bool
    media: list[str] = []
    warnings: list[str] = []
    published_url: str | None = None
    published_at: datetime | None = None
    published_text: str | None = None

    @field_validator("generated_at", "published_at")
    @classmethod
    def _aware(cls, v: datetime | None) -> datetime | None:
        if v is not None and v.tzinfo is None:
            raise ValueError("datetime must be timezone-aware")
        return v


@dataclass
class Draft:
    meta: DraftMeta
    variants: list[str]
    path: Path


def draft_id(campaign: str, beat: str, network: Network) -> str:
    return f"{campaign}--{beat}--{network.value}"


def draft_path(root: Path, draft_id: str) -> Path:
    return root / f"{draft_id}.md"


def _str_representer(dumper: yaml.SafeDumper, data: str) -> yaml.ScalarNode:
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


class _Dumper(yaml.SafeDumper):
    pass


_Dumper.add_representer(str, _str_representer)


def _meta_dict(meta: DraftMeta) -> dict[str, Any]:
    data = meta.model_dump(mode="json")
    # Keep datetimes as real YAML timestamps (tz-aware) instead of strings.
    for key in ("generated_at", "published_at"):
        value = getattr(meta, key)
        data[key] = value.isoformat() if value is not None else None
    return data


def render(meta: DraftMeta, variants: list[str]) -> str:
    head = yaml.dump(
        _meta_dict(meta),
        Dumper=_Dumper,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    )
    body = "\n\n".join(f"## Variant {i}\n\n{v.strip()}" for i, v in enumerate(variants, 1))
    return f"---\n{head}---\n\n{body}\n"


def parse(text: str, path: Path) -> Draft:
    try:
        post = frontmatter.loads(text)
        meta = DraftMeta.model_validate(post.metadata)
    except (ValidationError, TypeError, yaml.YAMLError) as e:
        raise DraftError(f"{path}: invalid front matter: {e}") from e
    body: str = post.content
    matches = list(VARIANT_RE.finditer(body))
    numbers = [int(m.group(1)) for m in matches]
    if numbers != list(range(1, len(numbers) + 1)):
        raise DraftError(f"{path}: variant headings must be 1..N consecutive, found {numbers}")
    if body[: matches[0].start() if matches else len(body)].strip():
        raise DraftError(f"{path}: unexpected text before the first variant heading")
    if meta.variants != len(matches):
        raise DraftError(
            f"{path}: front matter says {meta.variants} variants but body has {len(matches)}"
        )
    if meta.chosen is not None and not 1 <= meta.chosen <= len(matches):
        raise DraftError(
            f"{path}: chosen={meta.chosen} does not match any of the {len(matches)} variants"
        )
    variants = []
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        variants.append(body[m.end() : end].strip())
    return Draft(meta=meta, variants=variants, path=path)


def load(path: Path) -> Draft:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise DraftError(f"{path}: cannot read draft: {e}") from e
    return parse(text, path)


def save(draft: Draft) -> None:
    draft.path.parent.mkdir(parents=True, exist_ok=True)
    text = render(draft.meta, draft.variants)
    fd, tmp = tempfile.mkstemp(dir=draft.path.parent, prefix=f".{draft.path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        os.replace(tmp, draft.path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def chosen_text(draft: Draft) -> str:
    if draft.meta.chosen is None:
        raise DraftError(f"{draft.path}: no variant has been chosen")
    return draft.variants[draft.meta.chosen - 1]


def _require(draft: Draft, allowed: set[Status], action: str) -> None:
    if draft.meta.status not in allowed:
        raise DraftError(f"{draft.path}: cannot {action} a draft with status {draft.meta.status}")


def approve(path: Path) -> Draft:
    draft = load(path)
    _require(draft, {Status.draft}, "approve")
    if draft.meta.chosen is None:
        raise DraftError(f"{path}: cannot approve without a chosen variant")
    draft.meta.status = Status.approved
    save(draft)
    return draft


def unapprove(path: Path) -> Draft:
    draft = load(path)
    _require(draft, {Status.approved}, "unapprove")
    draft.meta.status = Status.draft
    save(draft)
    return draft


def mark_posted(path: Path, url: str, text: str | None, now: datetime) -> Draft:
    draft = load(path)
    _require(draft, {Status.approved}, "mark as posted")
    published = text if text is not None else chosen_text(draft)
    draft.meta.published_url = url
    draft.meta.published_at = now if now.tzinfo else now.replace(tzinfo=UTC)
    draft.meta.published_text = published
    draft.meta.status = Status.posted
    save(draft)
    return draft


def add_media(path: Path, files: list[Path]) -> Draft:
    draft = load(path)
    if draft.meta.status in {Status.scheduled, Status.posted}:
        raise DraftError(f"{path}: cannot add media to a {draft.meta.status} draft")
    for f in files:
        if not f.is_file():
            raise DraftError(f"{path}: media file does not exist: {f}")
    draft.meta.media.extend(str(f) for f in files)
    save(draft)
    return draft
