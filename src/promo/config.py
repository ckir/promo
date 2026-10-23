"""Settings and generator profiles loaded from promo.toml."""

import os
import tomllib
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


class ConfigError(ValueError):
    """Raised for an unreadable or invalid promo.toml, or a missing secret."""


def _machine_timezone() -> str:
    """IANA name of the machine zone from /etc/localtime, or UTC if unresolvable."""
    try:
        target = Path("/etc/localtime").resolve(strict=True)
        parts = target.parts
        name = "/".join(parts[parts.index("zoneinfo") + 1 :])
        ZoneInfo(name)
        return name
    except (OSError, ValueError, ZoneInfoNotFoundError):
        return "UTC"


class Profile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["anthropic", "openai-compatible"]
    model: str
    api_key_env: str | None = None
    base_url: str | None = None
    effort: str = "high"
    max_tokens: int = 4096
    trains_on_input: bool = False


class NetworkOverride(BaseModel):
    model_config = ConfigDict(extra="forbid")

    limit: int | None = None
    hashtag_cap: int | None = None


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    variants_per_draft: int = Field(3, ge=1, le=9)
    timezone: str = Field(default_factory=_machine_timezone)
    networks: dict[str, NetworkOverride] = Field(default_factory=dict)
    default_profile: str
    profiles: dict[str, Profile] = Field(default_factory=dict)

    @field_validator("timezone")
    @classmethod
    def _valid_zone(cls, v: str) -> str:
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError, OSError) as e:
            raise ValueError(f"timezone {v!r} is not a valid IANA name") from e
        return v

    @model_validator(mode="after")
    def _default_exists(self) -> "Settings":
        if self.default_profile not in self.profiles:
            raise ValueError(f"generator.default {self.default_profile!r} is not a defined profile")
        return self

    def profile(self, name: str | None) -> Profile:
        """Return the named profile; None selects the configured default."""
        key = self.default_profile if name is None else name
        try:
            return self.profiles[key]
        except KeyError:
            known = ", ".join(sorted(self.profiles)) or "none"
            raise ConfigError(f"unknown profile {key!r} (defined: {known})") from None


class _Generator(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default: str


def load_settings(path: Path = Path("promo.toml")) -> Settings:
    try:
        with open(path, "rb") as f:
            raw: dict[str, Any] = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError) as e:
        raise ConfigError(f"{path}: {e}") from e
    try:
        generator = _Generator.model_validate(raw.pop("generator", None) or {})
        return Settings.model_validate({**raw, "default_profile": generator.default})
    except ValidationError as e:
        raise ConfigError(f"{path}: {e}") from e


def resolve_api_key(profile: Profile) -> str | None:
    """Load .env, then read the profile's key variable; None when it needs none."""
    if profile.api_key_env is None:
        return None
    load_dotenv()
    value = os.environ.get(profile.api_key_env)
    if not value:
        raise ConfigError(f"environment variable {profile.api_key_env} is not set")
    return value
