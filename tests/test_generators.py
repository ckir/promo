from types import SimpleNamespace
from typing import Any

import anthropic
import httpx2
import pytest
from pydantic import ValidationError

from promo.config import Profile
from promo.generators import (
    GenerationError,
    GenerationRequest,
    Variants,
    make_generator,
)
from promo.generators.anthropic import AnthropicGenerator
from promo.generators.fake import FakeGenerator


def _req(user: str = "write about the launch", n: int = 3) -> GenerationRequest:
    return GenerationRequest(system="sys prompt", user=user, n_variants=n)


def _profile(**kw: Any) -> Profile:
    base: dict[str, Any] = {
        "kind": "anthropic",
        "model": "claude-opus-5-5",
        "effort": "high",
        "max_tokens": 4096,
    }
    base.update(kw)
    return Profile(**base)


class StubClient:
    def __init__(self, response: Any = None, error: Exception | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self._response = response
        self._error = error
        self.messages = SimpleNamespace(parse=self._parse)

    def _parse(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        return self._response


def _response(
    variants: list[str] | None = None,
    stop_reason: str = "end_turn",
    parsed: Any = "default",
) -> Any:
    if parsed == "default":
        parsed = Variants(variants=variants or ["a", "b"])
    return SimpleNamespace(
        parsed_output=parsed,
        stop_reason=stop_reason,
        usage=SimpleNamespace(input_tokens=11, output_tokens=7),
        model="claude-opus-5-5-20260101",
    )


def _gen(client: StubClient, **kw: Any) -> AnthropicGenerator:
    return AnthropicGenerator(_profile(**kw), "k", client=client)  # type: ignore[arg-type]


def test_fake_returns_scripted_variants_in_order() -> None:
    fake = FakeGenerator([["a", "b"], ["c"]])
    assert fake.generate(_req()).variants == ["a", "b"]
    assert fake.generate(_req()).variants == ["c"]
    with pytest.raises(GenerationError):
        fake.generate(_req())


def test_fake_default_is_deterministic_and_sized() -> None:
    fake = FakeGenerator()
    req = _req(user="x" * 100, n=3)
    result = fake.generate(req)
    assert result.variants == [f"{'x' * 40} v{i}" for i in (1, 2, 3)]
    assert fake.generate(req).variants == result.variants
    assert result.model == "fake"


def test_fake_records_requests() -> None:
    fake = FakeGenerator()
    r1, r2 = _req("one"), _req("two")
    fake.generate(r1)
    fake.generate(r2)
    assert fake.requests == [r1, r2]


def test_fake_usage_formulas() -> None:
    fake = FakeGenerator([["x" * 20, "y" * 20]])
    result = fake.generate(GenerationRequest(system="s" * 8, user="u" * 12, n_variants=2))
    assert result.usage.input_tokens == 5
    assert result.usage.output_tokens == 10


def test_fake_fail_after_raises_generation_error() -> None:
    fake = FakeGenerator(fail_after=2)
    fake.generate(_req())
    fake.generate(_req())
    with pytest.raises(GenerationError):
        fake.generate(_req())
    assert len(fake.requests) == 3


def test_fake_fail_after_zero_fails_immediately() -> None:
    with pytest.raises(GenerationError):
        FakeGenerator(fail_after=0).generate(_req())


def test_variants_requires_at_least_one() -> None:
    with pytest.raises(ValidationError):
        Variants(variants=[])


def test_anthropic_generator_builds_expected_request() -> None:
    client = StubClient(_response())
    request = _req()
    _gen(client).generate(request)
    (kwargs,) = client.calls
    assert kwargs["model"] == "claude-opus-5-5"
    assert kwargs["max_tokens"] == 4096
    assert kwargs["system"] == request.system
    assert kwargs["messages"] == [{"role": "user", "content": request.user}]
    assert kwargs["output_format"] is Variants
    assert kwargs["output_config"] == {"effort": "high"}


def test_anthropic_generator_maps_usage_and_model() -> None:
    result = _gen(StubClient(_response(["p", "q", "r"]))).generate(_req())
    assert result.variants == ["p", "q", "r"]
    assert result.usage.input_tokens == 11
    assert result.usage.output_tokens == 7
    assert result.model == "claude-opus-5-5-20260101"


def test_anthropic_generator_refusal_raises() -> None:
    client = StubClient(_response(stop_reason="refusal", parsed=None))
    with pytest.raises(GenerationError, match="model refused the request"):
        _gen(client).generate(_req())


def test_anthropic_generator_missing_parsed_output_raises() -> None:
    client = StubClient(_response(parsed=None))
    with pytest.raises(GenerationError, match="no structured output"):
        _gen(client).generate(_req())


def test_anthropic_generator_wraps_connection_error() -> None:
    err = anthropic.APIConnectionError(
        request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    )
    with pytest.raises(GenerationError, match="Anthropic connection error"):
        _gen(StubClient(error=err)).generate(_req())


def test_anthropic_generator_wraps_status_error() -> None:
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    err = anthropic.APIStatusError(
        "slow down", response=httpx2.Response(429, request=request), body=None
    )
    with pytest.raises(GenerationError) as info:
        _gen(StubClient(error=err)).generate(_req())
    assert str(info.value) == "Anthropic API error 429: slow down"


def test_anthropic_generator_rejects_unknown_effort() -> None:
    with pytest.raises(GenerationError, match="unsupported effort 'turbo'"):
        AnthropicGenerator(_profile(effort="turbo"), "k")


def test_anthropic_generator_builds_default_client() -> None:
    gen = AnthropicGenerator(_profile(), "k")
    assert isinstance(gen, AnthropicGenerator)


def test_make_generator_anthropic() -> None:
    assert isinstance(make_generator(_profile(), "k"), AnthropicGenerator)


def test_make_generator_requires_api_key() -> None:
    with pytest.raises(GenerationError, match="ANTHROPIC api key missing"):
        make_generator(_profile(), None)


def test_make_generator_rejects_openai_compatible_in_m1() -> None:
    profile = _profile(kind="openai-compatible", base_url="http://x")
    with pytest.raises(GenerationError) as info:
        make_generator(profile, "k")
    assert str(info.value) == "profile kind 'openai-compatible' arrives in milestone 1b"
