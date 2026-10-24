from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NamedTuple

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


@pytest.fixture
def manifest(fixture_ok: Path):
    from promo.schema import load_manifest

    m = load_manifest(fixture_ok)
    product = m.product.model_copy(
        update={"proof_points": ["Cuts setup time by 40%"], "target_url": "https://e.com/p"}
    )
    return m.model_copy(update={"product": product})


class CampaignDir(NamedTuple):
    manifest: Any
    campaign: str
    drafts_root: Path
    settings: Any
    brand: Path

    def with_beats(self, beats: list[dict[str, Any]]) -> Any:
        """Return the manifest with its beats replaced."""
        from promo.schema import Beat

        return self.manifest.model_copy(update={"beats": [Beat(**b) for b in beats]})


@pytest.fixture
def campaign_dir(tmp_path: Path) -> CampaignDir:
    from promo.config import Profile, Settings
    from promo.schema import Manifest

    brand = tmp_path / "brand.md"
    brand.write_text((FIXTURES / "brand.md").read_text(encoding="utf-8"), encoding="utf-8")
    manifest = Manifest.model_validate(
        {
            "product": {
                "name": "Acme Widget",
                "tagline": "Widgets that just work",
                "problem_statement": "Widgets break too often.",
                "key_features": ["Unbreakable casing", "One-click setup"],
                "target_url": "https://example.com/widget",
                "audience": "Makers and hobbyists",
                "proof_points": ["Used by twelve teams in beta"],
                "prohibited_claims": ["guaranteed"],
                "disclosures": [],
            },
            "brand_voice": str(brand),
            "launch_date": "2026-11-03",
            "beats": [
                {
                    "id": "teaser",
                    "offset_days": -2,
                    "intent": "teaser",
                    "networks": ["x", "linkedin"],
                },
                {
                    "id": "launch",
                    "offset_days": 0,
                    "intent": "launch",
                    "networks": ["x", "linkedin"],
                },
            ],
        }
    )
    settings = Settings(
        variants_per_draft=3,
        timezone="UTC",
        default_profile="claude",
        profiles={
            "claude": Profile(kind="anthropic", model="claude-test"),
            "alt": Profile(kind="anthropic", model="alt-model", api_key_env="ALT_KEY"),
            "trainer": Profile(kind="anthropic", model="trainer-model", trains_on_input=True),
        },
    )
    return CampaignDir(
        manifest=manifest,
        campaign="spring-launch",
        drafts_root=tmp_path / "drafts",
        settings=settings,
        brand=brand,
    )
