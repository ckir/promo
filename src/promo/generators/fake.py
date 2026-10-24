"""Deterministic in-memory generator for tests and dry runs."""

from promo.drafts import Usage
from promo.generators import GenerationError, GenerationRequest, GenerationResult


class FakeGenerator:
    def __init__(
        self,
        responses: list[list[str]] | None = None,
        *,
        fail_after: int | None = None,
    ) -> None:
        self._responses = responses
        self._fail_after = fail_after
        self._served = 0
        self.requests: list[GenerationRequest] = []

    def generate(self, request: GenerationRequest) -> GenerationResult:
        self.requests.append(request)
        if self._fail_after is not None and self._served >= self._fail_after:
            raise GenerationError("fake generator failure")
        if self._responses is not None:
            if self._served >= len(self._responses):
                raise GenerationError("fake generator has no scripted response left")
            variants = list(self._responses[self._served])
        else:
            variants = [f"{request.user[:40]} v{i}" for i in range(1, request.n_variants + 1)]
        self._served += 1
        return GenerationResult(
            variants=variants,
            usage=Usage(
                input_tokens=len(request.system + request.user) // 4,
                output_tokens=sum(len(v) for v in variants) // 4,
            ),
            model="fake",
        )
