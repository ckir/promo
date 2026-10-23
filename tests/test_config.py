from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from promo.config import ConfigError, Profile, load_settings, resolve_api_key

REPO_ROOT = Path(__file__).parent.parent


def test_default_profile_is_claude_opus(tmp_toml: Path) -> None:
    s = load_settings(tmp_toml)
    assert s.profile(None).model == "claude-opus-5-5"


def test_unknown_profile_raises(tmp_toml: Path) -> None:
    with pytest.raises(ConfigError):
        load_settings(tmp_toml).profile("nope")


def test_missing_api_key_names_variable(
    tmp_toml: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ConfigError, match="ANTHROPIC_API_KEY"):
        resolve_api_key(load_settings(tmp_toml).profile(None))


def test_api_key_resolved_from_environment(
    tmp_toml: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    assert resolve_api_key(load_settings(tmp_toml).profile(None)) == "sk-test"


def test_profile_without_key_env_resolves_none() -> None:
    assert resolve_api_key(Profile(kind="openai-compatible", model="m")) is None


def test_timezone_defaults_to_machine_zone(tmp_toml_no_tz: Path) -> None:
    tz = load_settings(tmp_toml_no_tz).timezone
    assert tz
    ZoneInfo(tz)


def test_explicit_timezone_is_kept(tmp_toml: Path) -> None:
    assert load_settings(tmp_toml).timezone == "Europe/Athens"


def test_invalid_timezone_rejected(tmp_path: Path) -> None:
    p = tmp_path / "promo.toml"
    p.write_text('timezone = "Not/AZone"\n[generator]\ndefault = "c"\n')
    with pytest.raises(ConfigError):
        load_settings(p)


def test_unknown_toml_key_rejected(tmp_toml_bad: Path) -> None:
    with pytest.raises(ConfigError):
        load_settings(tmp_toml_bad)


def test_unknown_key_in_profile_rejected(tmp_path: Path) -> None:
    p = tmp_path / "promo.toml"
    p.write_text(
        '[generator]\ndefault = "c"\n[profiles.c]\nkind = "anthropic"\nmodel = "m"\nzzz = 1\n'
    )
    with pytest.raises(ConfigError):
        load_settings(p)


def test_missing_file_raises_config_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        load_settings(tmp_path / "absent.toml")


def test_variants_per_draft_bounds(tmp_path: Path) -> None:
    p = tmp_path / "promo.toml"
    p.write_text('variants_per_draft = 10\n[generator]\ndefault = "c"\n')
    with pytest.raises(ConfigError):
        load_settings(p)


def test_default_must_name_existing_profile(tmp_path: Path) -> None:
    p = tmp_path / "promo.toml"
    p.write_text('[generator]\ndefault = "ghost"\n')
    with pytest.raises(ConfigError):
        load_settings(p)


def test_network_override_loaded(tmp_toml: Path) -> None:
    assert load_settings(tmp_toml).networks["x"].limit == 280


def test_repo_promo_toml_default_profile() -> None:
    s = load_settings(REPO_ROOT / "promo.toml")
    p = s.profile(None)
    assert s.default_profile == "claude"
    assert (p.kind, p.model, p.api_key_env) == ("anthropic", "claude-opus-5-5", "ANTHROPIC_API_KEY")
    assert (p.effort, p.max_tokens, p.trains_on_input) == ("high", 4096, False)
    assert s.variants_per_draft == 3
