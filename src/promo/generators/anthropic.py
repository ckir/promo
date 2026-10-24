"""Anthropic Messages API generator using structured outputs."""

from typing import Literal, cast

import anthropic

from promo.config import Profile
from promo.drafts import Usage
from promo.generators import (
    GenerationError,
    GenerationRequest,
    GenerationResult,
    Variants,
)

Effort = Literal["low", "medium", "high", "xhigh", "max"]
_EFFORTS = ("low", "medium", "high", "xhigh", "max")


class AnthropicGenerator:
    def __init__(
        self,
        profile: Profile,
        api_key: str,
        client: anthropic.Anthropic | None = None,
    ) -> None:
        if profile.effort not in _EFFORTS:
            raise GenerationError(f"unsupported effort {profile.effort!r}")
        self._profile = profile
        self._effort = cast(Effort, profile.effort)
        self._client = client or anthropic.Anthropic(api_key=api_key)

    def generate(self, request: GenerationRequest) -> GenerationResult:
        try:
            response = self._client.messages.parse(
                model=self._profile.model,
                max_tokens=self._profile.max_tokens,
                system=request.system,
                messages=[{"role": "user", "content": request.user}],
                output_format=Variants,
                output_config={"effort": self._effort},
            )
        except anthropic.APIStatusError as e:
            raise GenerationError(f"Anthropic API error {e.status_code}: {e.message}") from e
        except anthropic.APIConnectionError as e:
            raise GenerationError(f"Anthropic connection error: {e}") from e
        if response.stop_reason == "refusal":
            raise GenerationError("model refused the request")
        parsed = response.parsed_output
        if parsed is None:
            raise GenerationError("model returned no structured output")
        return GenerationResult(
            variants=list(parsed.variants),
            usage=Usage(
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
            ),
            model=response.model,
        )
