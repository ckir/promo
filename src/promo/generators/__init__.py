# Copyright (c) 2026 Costas Kirgoussios
#
# This software is licensed under the PolyForm Noncommercial License 1.0.0.
# You may obtain a copy of the License at:
# https://polyformproject.org/licenses/noncommercial/1.0.0/

"""Generator protocol and factory."""

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field

from promo.config import Profile
from promo.drafts import Usage


class GenerationError(RuntimeError):
    """A generator could not produce variants."""


class Variants(BaseModel):
    variants: list[str] = Field(min_length=1)


class GenerationRequest(BaseModel):
    system: str
    user: str
    n_variants: int


class GenerationResult(BaseModel):
    variants: list[str]
    usage: Usage
    model: str


@runtime_checkable
class Generator(Protocol):
    def generate(self, request: GenerationRequest) -> GenerationResult: ...


def make_generator(profile: Profile, api_key: str | None) -> Generator:
    if profile.kind == "anthropic":
        if api_key is None:
            raise GenerationError("ANTHROPIC api key missing")
        from promo.generators.anthropic import AnthropicGenerator

        return AnthropicGenerator(profile, api_key)
    raise GenerationError(f"profile kind {profile.kind!r} arrives in milestone 1b")
