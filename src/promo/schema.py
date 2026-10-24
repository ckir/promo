"""Campaign manifest schema (spec section 5)."""

import re
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Self

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator, model_validator

SLUG_RE = re.compile(r"^[a-z0-9-]+$")


class ManifestError(ValueError):
    """A manifest could not be read or failed validation."""


class Network(StrEnum):
    x = "x"
    linkedin = "linkedin"
    threads = "threads"
    mastodon = "mastodon"
    bluesky = "bluesky"
    instagram = "instagram"
    facebook = "facebook"
    tiktok = "tiktok"
    pinterest = "pinterest"


class Intent(StrEnum):
    teaser = "teaser"
    launch = "launch"
    deep_dive = "deep-dive"
    social_proof = "social-proof"
    custom = "custom"


class Product(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    tagline: str
    problem_statement: str
    key_features: list[str]
    target_url: str
    audience: str
    proof_points: list[str]
    prohibited_claims: list[str]
    disclosures: list[str]


class Beat(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    offset_days: int
    intent: Intent
    networks: list[Network]
    notes: str | None = None

    @field_validator("id")
    @classmethod
    def _id_is_slug(cls, v: str) -> str:
        if not SLUG_RE.fullmatch(v):
            raise ValueError(f"beat id {v!r} must match [a-z0-9-]+")
        return v

    @model_validator(mode="after")
    def _custom_needs_notes(self) -> Self:
        if self.intent is Intent.custom and not (self.notes and self.notes.strip()):
            raise ValueError(f"beat {self.id!r}: intent custom requires notes")
        return self


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product: Product
    brand_voice: Path
    confidential: bool = True
    launch_date: date
    beats: list[Beat]

    @model_validator(mode="after")
    def _check_beats(self) -> Self:
        if not self.beats:
            raise ValueError("manifest must have at least one beat")
        ids = [b.id for b in self.beats]
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        if dupes:
            raise ValueError(f"duplicate beat ids: {', '.join(dupes)}")
        if not self.product.proof_points and any(
            b.intent is Intent.social_proof for b in self.beats
        ):
            raise ValueError("a social-proof beat requires non-empty product.proof_points")
        return self


def load_manifest(path: Path) -> Manifest:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        return Manifest.model_validate(raw)
    except (OSError, UnicodeDecodeError, yaml.YAMLError, ValidationError) as e:
        raise ManifestError(f"{path}: {e}") from e
