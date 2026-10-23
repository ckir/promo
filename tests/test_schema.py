import copy
from pathlib import Path
from typing import Any

import pytest
import yaml

from promo.schema import ManifestError, load_manifest


def _write(tmp_path: Path, fixture_ok: Path, mutate: Any) -> Path:
    data = yaml.safe_load(fixture_ok.read_text())
    data = copy.deepcopy(data)
    mutate(data)
    out = tmp_path / "manifest.yaml"
    out.write_text(yaml.safe_dump(data))
    return out


def test_loads_valid_manifest(fixture_ok: Path) -> None:
    m = load_manifest(fixture_ok)
    assert m.beats[0].id == "teaser"


def test_unknown_field_rejected(tmp_path: Path, fixture_ok: Path) -> None:
    p = _write(tmp_path, fixture_ok, lambda d: d["product"].update(extra_key="x"))
    with pytest.raises(ManifestError) as exc:
        load_manifest(p)
    assert str(p) in str(exc.value)


def test_zero_beats_rejected(tmp_path: Path, fixture_ok: Path) -> None:
    p = _write(tmp_path, fixture_ok, lambda d: d.update(beats=[]))
    with pytest.raises(ManifestError):
        load_manifest(p)


def test_duplicate_beat_ids_rejected(tmp_path: Path, fixture_ok: Path) -> None:
    p = _write(tmp_path, fixture_ok, lambda d: d["beats"][1].update(id="teaser"))
    with pytest.raises(ManifestError):
        load_manifest(p)


def test_beat_id_must_be_slug(tmp_path: Path, fixture_ok: Path) -> None:
    p = _write(tmp_path, fixture_ok, lambda d: d["beats"][0].update(id="Teaser 1"))
    with pytest.raises(ManifestError):
        load_manifest(p)


def test_custom_intent_requires_notes(tmp_path: Path, fixture_ok: Path) -> None:
    p = _write(tmp_path, fixture_ok, lambda d: d["beats"][0].update(intent="custom"))
    with pytest.raises(ManifestError):
        load_manifest(p)


def test_social_proof_requires_proof_points(tmp_path: Path, fixture_ok: Path) -> None:
    def mutate(d: dict[str, Any]) -> None:
        d["product"]["proof_points"] = []
        d["beats"][0]["intent"] = "social-proof"

    with pytest.raises(ManifestError):
        load_manifest(_write(tmp_path, fixture_ok, mutate))


def test_confidential_defaults_true(fixture_ok: Path) -> None:
    assert load_manifest(fixture_ok).confidential is True


def test_unknown_network_rejected(tmp_path: Path, fixture_ok: Path) -> None:
    p = _write(tmp_path, fixture_ok, lambda d: d["beats"][0].update(networks=["youtube"]))
    with pytest.raises(ManifestError):
        load_manifest(p)
