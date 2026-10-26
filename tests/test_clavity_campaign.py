# Copyright (c) 2026 Costas Kirgoussios
#
# This software is licensed under the PolyForm Noncommercial License 1.0.0.
# You may obtain a copy of the License at:
# https://polyformproject.org/licenses/noncommercial/1.0.0/

import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from promo.cli import app
from promo.networks import HASHTAG_CAPS, LIMITS
from promo.postprocess import finalize, prohibited_matches
from promo.prompts import load_brand_voice
from promo.schema import Beat, Intent, Manifest, Network, load_manifest

REPO = Path(__file__).parent.parent
CAMPAIGN = REPO / "campaigns" / "clavity"
PROHIBITED = {
    "completely free",
    "free for any use",
    "catches every bug",
    "no bugs",
    "independently verified",
    "guaranteed",
    "production-ready",
}
REQUIRED = {
    "case-study": ("own ledger", "one example", "not a rate"),
    "install-comment": (
        "superpowers",
        "Antigravity",
        "PolyForm Noncommercial 1.0.0",
        "personal, academic and non-profit use only",
        "mutually exclusive",
    ),
}


def _manifest() -> Manifest:
    return load_manifest(CAMPAIGN / "manifest.yaml")


def _beats(m: Manifest) -> dict[str, Beat]:
    return {b.id: b for b in m.beats}


def test_manifest_shape() -> None:
    m = _manifest()
    beats = _beats(m)
    assert list(beats) == ["case-study", "install-comment", "addon-replies"]
    assert beats["case-study"].intent is Intent.deep_dive
    assert beats["install-comment"].intent is Intent.custom
    assert beats["addon-replies"].intent is Intent.custom
    assert all(b.networks == [Network.facebook] and b.offset_days == 0 for b in m.beats)
    assert m.confidential is False
    assert m.product.target_url == "https://github.com/ckir/clavity"
    assert m.product.disclosures == ["I'm the author of clavity."]
    assert set(m.product.prohibited_claims) == PROHIBITED


def test_proof_points_carry_the_ledger_figures() -> None:
    joined = "\n".join(_manifest().product.proof_points)
    for needle in ("3adc045", "KEEP=5 kept 4 slots", "KEEP=0, abc and -1 kept 0", "tail -n +1"):
        assert needle in joined


def test_required_wording_does_not_trip_prohibited_claims() -> None:
    m = _manifest()
    for beat_id, phrases in REQUIRED.items():
        notes = _beats(m)[beat_id].notes or ""
        for phrase in phrases:
            assert phrase in notes, (beat_id, phrase)
            assert prohibited_matches(phrase, m.product.prohibited_claims) == [], phrase


def test_case_study_notes_forbid_links() -> None:
    notes = _beats(_manifest())["case-study"].notes or ""
    assert "Do not include any link or install command" in notes


def test_install_comment_notes_carry_exact_commands() -> None:
    notes = _beats(_manifest())["install-comment"].notes or ""
    assert "claude plugin marketplace add ckir/clavity" in notes
    assert "claude plugin install clavity@clavity" in notes


def test_addon_notes_name_the_three_plugins() -> None:
    notes = _beats(_manifest())["addon-replies"].notes or ""
    for plugin in ("agy-autotrain", "commonmemory", "review-relay"):
        assert f"claude plugin install {plugin}@clavity" in notes


def test_brand_examples_pass_post_processing() -> None:
    m = _manifest()
    _, examples = load_brand_voice(REPO / m.brand_voice)
    lines = [ln for ln in examples.splitlines() if ln.strip()]
    assert lines
    for line in lines:
        text, warnings = finalize(
            line,
            manifest=m,
            beat=_beats(m)["case-study"],
            network=Network.facebook,
            campaign="clavity",
            limit=LIMITS[Network.facebook],
            hashtag_cap=HASHTAG_CAPS[Network.facebook],
        )
        assert warnings == [], (line, warnings)
        assert "I'm the author of clavity." in text


def test_dry_run_counts_three_calls(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    shutil.copy(REPO / "promo.toml", tmp_path / "promo.toml")
    shutil.copytree(CAMPAIGN, tmp_path / "campaigns" / "clavity")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    result = CliRunner().invoke(app, ["draft", "clavity", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "dry run: 3 model call(s) would be made" in result.output
