import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from promo import drafts
from promo.cli import app
from promo.drafts import Status, draft_path
from promo.generators.fake import FakeGenerator
from promo.prompts import load_brand_voice
from promo.schema import load_manifest

REPO = Path(__file__).parent.parent
TEASER_X = "example/teaser/x"


@pytest.fixture
def workdir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    shutil.copy(REPO / "promo.toml", tmp_path / "promo.toml")
    shutil.copy(REPO / "brand.md", tmp_path / "brand.md")
    shutil.copytree(REPO / "campaigns" / "example", tmp_path / "campaigns" / "example")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setattr("promo.cli.make_generator", lambda profile, key: FakeGenerator())
    return tmp_path


def _generate(*extra: str) -> None:
    result = CliRunner().invoke(app, ["draft", "example", *extra])
    assert result.exit_code == 0, result.output


def _approve(draft_id: str) -> Path:
    path = draft_path(Path("drafts"), draft_id)
    d = drafts.load(path)
    if d.meta.chosen is None:
        d.meta.chosen = 1
        drafts.save(d)
    drafts.approve(path)
    return path


def test_draft_dry_run_prints_call_count(workdir: Path) -> None:
    result = CliRunner().invoke(app, ["draft", "example", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "dry run: 4 model call(s) would be made" in result.output
    assert not (workdir / "drafts").exists()


def test_draft_dry_run_needs_no_api_key(workdir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    result = CliRunner().invoke(app, ["draft", "example", "--dry-run"])
    assert result.exit_code == 0, result.output


def test_draft_writes_files_and_exits_zero(workdir: Path) -> None:
    result = CliRunner().invoke(app, ["draft", "example"])
    assert result.exit_code == 0, result.output
    for did in (
        "example/teaser/x",
        "example/teaser/linkedin",
        "example/launch/x",
        "example/launch/linkedin",
    ):
        assert f"generated {did}" in result.output
        assert (workdir / "drafts" / f"{did}.md").is_file()
    assert "4 model call(s)" in result.output
    again = CliRunner().invoke(app, ["draft", "example"])
    assert again.exit_code == 0
    assert f"skipped {TEASER_X}" in again.output
    assert "0 model call(s)" in again.output


def test_draft_missing_api_key_exit_1_names_variable(
    workdir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    result = CliRunner().invoke(app, ["draft", "example"])
    assert result.exit_code == 1
    assert "ANTHROPIC_API_KEY" in result.stderr
    assert not (workdir / "drafts").exists()


def test_draft_traversal_campaign_name_exit_1(workdir: Path) -> None:
    result = CliRunner().invoke(app, ["draft", "../x"])
    assert result.exit_code == 1
    assert "campaign name" in result.stderr
    assert not (workdir / "drafts").exists()


def test_draft_force_does_not_touch_posted(workdir: Path) -> None:
    _generate()
    path = _approve(TEASER_X)
    done = CliRunner().invoke(app, ["posted", TEASER_X, "--url", "https://x.example/status/1"])
    assert done.exit_code == 0, done.output
    before = path.read_text(encoding="utf-8")
    result = CliRunner().invoke(app, ["draft", "example", "--force"])
    assert result.exit_code == 0, result.output
    assert f"skipped {TEASER_X}" in result.output
    assert f"generated {TEASER_X}" not in result.output
    assert path.read_text(encoding="utf-8") == before


def test_posted_requires_http_url(workdir: Path) -> None:
    _generate()
    _approve(TEASER_X)
    for bad in ("ftp://x.example/1", "not a url", "https://"):
        result = CliRunner().invoke(app, ["posted", TEASER_X, "--url", bad])
        assert result.exit_code == 1
        assert "--url must be an http(s) URL" in result.stderr
    assert drafts.load(draft_path(Path("drafts"), TEASER_X)).meta.status is Status.approved


def test_posted_then_file_has_published_fields(workdir: Path) -> None:
    _generate()
    path = _approve(TEASER_X)
    text_file = workdir / "final.txt"
    text_file.write_text("Final posted words", encoding="utf-8")
    result = CliRunner().invoke(
        app,
        ["posted", TEASER_X, "--url", "https://x.example/status/1", "--text-file", str(text_file)],
    )
    assert result.exit_code == 0, result.output
    assert f"posted {TEASER_X}" in result.output
    meta = drafts.load(path).meta
    assert meta.status is Status.posted
    assert meta.published_url == "https://x.example/status/1"
    assert meta.published_text == "Final posted words"
    assert meta.published_at is not None
    assert meta.published_at <= datetime.now(UTC)


def test_posted_missing_text_file_exit_1(workdir: Path) -> None:
    _generate()
    _approve(TEASER_X)
    result = CliRunner().invoke(
        app,
        ["posted", TEASER_X, "--url", "https://x.example/1", "--text-file", "nope.txt"],
    )
    assert result.exit_code == 1
    assert "cannot read --text-file" in result.stderr
    assert drafts.load(draft_path(Path("drafts"), TEASER_X)).meta.status is Status.approved


def test_unknown_draft_id_exits_1(workdir: Path) -> None:
    for argv in (
        ["posted", "example/nope/x", "--url", "https://x.example/1"],
        ["unapprove", "example/nope/x"],
        ["media", "example/nope/x", "a.png"],
        ["unapprove", "../etc/passwd"],
    ):
        result = CliRunner().invoke(app, argv)
        assert result.exit_code == 1, argv
        assert "no such draft" in result.stderr


def test_unapprove_on_draft_status_exits_1(workdir: Path) -> None:
    _generate()
    result = CliRunner().invoke(app, ["unapprove", TEASER_X])
    assert result.exit_code == 1
    assert "cannot unapprove" in result.stderr


def test_unapprove_approved_draft(workdir: Path) -> None:
    _generate()
    path = _approve(TEASER_X)
    result = CliRunner().invoke(app, ["unapprove", TEASER_X])
    assert result.exit_code == 0, result.output
    assert f"unapproved {TEASER_X}" in result.output
    assert drafts.load(path).meta.status is Status.draft


def test_media_records_existing_file(workdir: Path) -> None:
    _generate()
    pic = workdir / "pic.png"
    pic.write_bytes(b"png")
    result = CliRunner().invoke(app, ["media", TEASER_X, str(pic)])
    assert result.exit_code == 0, result.output
    assert f"media {TEASER_X}: 1 file(s)" in result.output
    assert drafts.load(draft_path(Path("drafts"), TEASER_X)).meta.media == [str(pic)]


def test_media_missing_file_exit_1(workdir: Path) -> None:
    _generate()
    result = CliRunner().invoke(app, ["media", TEASER_X, "missing.png"])
    assert result.exit_code == 1
    assert "does not exist" in result.stderr


def test_example_manifest_validates() -> None:
    manifest = load_manifest(REPO / "campaigns" / "example" / "manifest.yaml")
    assert [b.id for b in manifest.beats] == ["teaser", "launch"]
    assert manifest.confidential is True
    prose, examples = load_brand_voice(REPO / "brand.md")
    assert prose and examples


def test_posted_strips_surrounding_whitespace(workdir: Path) -> None:
    _generate()
    path = _approve(TEASER_X)
    result = CliRunner().invoke(app, ["posted", TEASER_X, "--url", "  https://x.example/1 \n"])
    assert result.exit_code == 0, result.output
    assert drafts.load(path).meta.published_url == "https://x.example/1"


@pytest.mark.parametrize(
    "bad",
    [
        "https://x.example/a b",
        "https://x.example/\nstatus: draft",
        "http://a\x00",
        "javascript:alert(1)",
        "file:///etc/passwd",
        "http://",
    ],
)
def test_posted_rejects_bad_urls_without_writing(workdir: Path, bad: str) -> None:
    _generate()
    path = _approve(TEASER_X)
    before = path.read_bytes()
    result = CliRunner().invoke(app, ["posted", TEASER_X, "--url", bad])
    assert result.exit_code == 1
    assert "--url must be an http(s) URL" in result.stderr
    assert path.read_bytes() == before


def test_posted_on_draft_status_exits_1_file_unchanged(workdir: Path) -> None:
    _generate()
    path = draft_path(Path("drafts"), TEASER_X)
    before = path.read_bytes()
    result = CliRunner().invoke(app, ["posted", TEASER_X, "--url", "https://x.example/1"])
    assert result.exit_code == 1
    assert "cannot mark as posted" in result.stderr
    assert path.read_bytes() == before


def test_draft_unknown_beat_exits_1(workdir: Path) -> None:
    result = CliRunner().invoke(app, ["draft", "example", "--beat", "nope"])
    assert result.exit_code == 1
    assert "unknown beat" in result.stderr
    assert not (workdir / "drafts").exists()


def test_draft_generation_error_mid_run_exits_1(
    workdir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "promo.cli.make_generator", lambda profile, key: FakeGenerator(fail_after=2)
    )
    result = CliRunner().invoke(app, ["draft", "example"])
    assert result.exit_code == 1
    assert "fake generator failure" in result.stderr
    written = sorted(p.name for p in (workdir / "drafts").rglob("*.md"))
    assert len(written) == 2


def test_draft_binary_manifest_exits_cleanly(workdir: Path) -> None:
    (workdir / "campaigns" / "example" / "manifest.yaml").write_bytes(b"\xff\xfe\x00")
    result = CliRunner().invoke(app, ["draft", "example", "--dry-run"])
    assert result.exit_code != 0
    assert "manifest.yaml" in result.stderr
    assert "Traceback" not in result.output
    assert not isinstance(result.exception, UnicodeDecodeError)


def test_posted_malformed_url_exits_cleanly(workdir: Path) -> None:
    _generate()
    _approve(TEASER_X)
    result = CliRunner().invoke(app, ["posted", TEASER_X, "--url", "http://[::1"])
    assert result.exit_code != 0
    assert "--url must be an http(s) URL" in result.stderr
    assert "Traceback" not in result.output
    assert not isinstance(result.exception, ValueError)
