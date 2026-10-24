# Copyright (c) 2026 Costas Kirgoussios
#
# This software is licensed under the PolyForm Noncommercial License 1.0.0.
# You may obtain a copy of the License at:
# https://polyformproject.org/licenses/noncommercial/1.0.0/

from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from promo.config import ConfigError, Profile, load_settings, resolve_api_key

REPO_ROOT = Path(__file__).parent.parent
_PROFILE_C = '[profiles.c]\nkind = "anthropic"\nmodel = "m"\n'


def _unset_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Absent key, recorded by monkeypatch so a load_dotenv() leak is undone at teardown."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.delenv("ANTHROPIC_API_KEY")


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
    _unset_key(monkeypatch)
    with pytest.raises(ConfigError, match="ANTHROPIC_API_KEY"):
        resolve_api_key(load_settings(tmp_toml).profile(None))


def test_dotenv_in_cwd_is_honoured(
    tmp_toml: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".env").write_text("ANTHROPIC_API_KEY=from-dotenv\n")
    monkeypatch.chdir(tmp_path)
    _unset_key(monkeypatch)
    assert resolve_api_key(load_settings(tmp_toml).profile(None)) == "from-dotenv"


def test_dotenv_outside_cwd_is_not_consulted(
    tmp_toml: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / ".env").write_text("ANTHROPIC_API_KEY=leak\n")
    workdir = tmp_path / "work"
    workdir.mkdir()
    monkeypatch.chdir(workdir)
    _unset_key(monkeypatch)
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
    p.write_text(f'timezone = "Not/AZone"\n[generator]\ndefault = "c"\n{_PROFILE_C}')
    with pytest.raises(ConfigError, match="timezone"):
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


@pytest.mark.parametrize("n", [0, 10])
def test_variants_per_draft_out_of_bounds_rejected(tmp_path: Path, n: int) -> None:
    p = tmp_path / "promo.toml"
    p.write_text(f'variants_per_draft = {n}\n[generator]\ndefault = "c"\n{_PROFILE_C}')
    with pytest.raises(ConfigError, match="variants_per_draft"):
        load_settings(p)


@pytest.mark.parametrize("n", [1, 9])
def test_variants_per_draft_in_bounds_accepted(tmp_path: Path, n: int) -> None:
    p = tmp_path / "promo.toml"
    p.write_text(f'variants_per_draft = {n}\n[generator]\ndefault = "c"\n{_PROFILE_C}')
    assert load_settings(p).variants_per_draft == n


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
