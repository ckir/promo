from datetime import UTC, datetime
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixture_ok() -> Path:
    return FIXTURES / "manifest_ok.yaml"


_TOML_BODY = """\
variants_per_draft = 3

[generator]
default = "claude"

[profiles.claude]
kind = "anthropic"
model = "claude-opus-5-5"
api_key_env = "ANTHROPIC_API_KEY"
effort = "high"
max_tokens = 4096
trains_on_input = false

[networks.x]
limit = 280
"""


@pytest.fixture
def tmp_toml(tmp_path: Path) -> Path:
    p = tmp_path / "promo.toml"
    p.write_text('timezone = "Europe/Athens"\n' + _TOML_BODY)
    return p


@pytest.fixture
def tmp_toml_no_tz(tmp_path: Path) -> Path:
    p = tmp_path / "promo.toml"
    p.write_text(_TOML_BODY)
    return p


@pytest.fixture
def tmp_toml_bad(tmp_path: Path) -> Path:
    p = tmp_path / "promo.toml"
    p.write_text(_TOML_BODY + "\nbogus_key = 1\n")
    return p


@pytest.fixture
def tmp_draft(tmp_path: Path) -> Path:
    from promo.drafts import Draft, DraftMeta, Status, Usage, save
    from promo.schema import Network

    meta = DraftMeta(
        id="camp/beat/x",
        campaign="camp",
        beat="beat",
        network=Network.x,
        status=Status.draft,
        variants=3,
        chosen=None,
        generated_at=datetime(2026, 10, 24, 9, 0, tzinfo=UTC),
        profile="claude",
        model="claude-opus-5-5",
        usage=Usage(input_tokens=10, output_tokens=20),
        needs_media=False,
    )
    path = tmp_path / "drafts" / "camp" / "beat" / "x.md"
    save(Draft(meta=meta, variants=["first", "second", "third"], path=path))
    return path
