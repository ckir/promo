import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from promo.drafts import (
    Draft,
    DraftError,
    DraftMeta,
    Status,
    Usage,
    add_media,
    approve,
    chosen_text,
    draft_id,
    draft_path,
    load,
    mark_posted,
    parse,
    render,
    save,
    unapprove,
)
from promo.schema import Network

NOW = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)


def _meta(**kw: object) -> DraftMeta:
    base: dict[str, object] = {
        "id": "camp/beat/x",
        "campaign": "camp",
        "beat": "beat",
        "network": Network.x,
        "status": Status.draft,
        "variants": 3,
        "chosen": None,
        "generated_at": datetime(2026, 10, 24, 9, 0, tzinfo=UTC),
        "profile": "claude",
        "model": "m",
        "usage": Usage(input_tokens=1, output_tokens=2),
        "needs_media": False,
    }
    base.update(kw)
    return DraftMeta(**base)  # type: ignore[arg-type]


def test_ids_and_paths(tmp_path: Path):
    did = draft_id("camp", "beat", Network.x)
    assert draft_path(tmp_path, did) == tmp_path / "camp" / "beat" / "x.md"
    assert draft_path(Path("drafts"), did) == Path("drafts/camp/beat/x.md")


@pytest.mark.parametrize("bad", ["../x", "a/../b", "/abs/x", "a//b", "a/./b", "./a"])
def test_draft_path_rejects_unsafe_ids(tmp_path: Path, bad: str):
    with pytest.raises(DraftError):
        draft_path(tmp_path, bad)


def test_render_parse_roundtrip():
    meta = _meta(chosen=2, warnings=["w"], media=["a.png"])
    variants = ["one\nline two", "two: with colon", "three"]
    text = render(meta, variants)
    keys = [ln.split(":")[0] for ln in text.split("---")[1].splitlines() if ln[:1].isalpha()]
    assert keys == [
        "id", "campaign", "beat", "network", "status", "variants", "chosen",
        "generated_at", "profile", "model", "usage", "needs_media", "media",
        "warnings", "published_url", "published_at", "published_text",
    ]  # fmt: skip
    d = parse(text, Path("x.md"))
    assert d.meta == meta
    assert d.meta.generated_at.tzinfo is not None
    assert d.variants == variants


def test_parse_rejects_missing_variant_heading():
    text = render(_meta(), ["a", "b", "c"]).replace("## Variant 2", "Variant 2")
    with pytest.raises(DraftError):
        parse(text, Path("x.md"))
    text = render(_meta(), ["a", "b", "c"]).replace("## Variant 2", "## Variant 3", 1)
    with pytest.raises(DraftError):
        parse(text, Path("x.md"))


def test_parse_rejects_chosen_out_of_range():
    with pytest.raises(DraftError, match="chosen"):
        parse(render(_meta(chosen=4), ["a", "b", "c"]), Path("x.md"))


def test_parse_rejects_chosen_whose_heading_was_removed():
    text = render(_meta(chosen=3, variants=2), ["a", "b", "c"][:2])
    with pytest.raises(DraftError, match="chosen"):
        parse(text, Path("x.md"))


def test_parse_rejects_variant_count_mismatch():
    with pytest.raises(DraftError, match="variants"):
        text = render(_meta(), ["a", "b", "c"]).replace("variants: 3", "variants: 2")
        parse(text, Path("x.md"))


def test_parse_rejects_bad_front_matter():
    with pytest.raises(DraftError):
        parse("---\nid: x\n---\n\n## Variant 1\n\na\n", Path("x.md"))


def test_approve_requires_chosen(tmp_draft: Path):
    with pytest.raises(DraftError):
        approve(tmp_draft)
    assert load(tmp_draft).meta.status == Status.draft


def _choose(path: Path, n: int = 2) -> None:
    d = load(path)
    d.meta.chosen = n
    save(d)


def test_approve_then_unapprove_keeps_text_and_chosen(tmp_draft: Path):
    _choose(tmp_draft)
    before = load(tmp_draft).variants
    approve(tmp_draft)
    assert load(tmp_draft).meta.status == Status.approved
    with pytest.raises(DraftError):
        approve(tmp_draft)
    unapprove(tmp_draft)
    d = load(tmp_draft)
    assert d.meta.status == Status.draft
    assert d.meta.chosen == 2
    assert d.variants == before
    with pytest.raises(DraftError):
        unapprove(tmp_draft)


def test_mark_posted_requires_approved(tmp_draft: Path):
    _choose(tmp_draft)
    with pytest.raises(DraftError):
        mark_posted(tmp_draft, "https://x/1", None, NOW)


def test_mark_posted_defaults_text_to_chosen_variant(tmp_draft: Path):
    _choose(tmp_draft)
    approve(tmp_draft)
    mark_posted(tmp_draft, "https://x/1", None, NOW)
    m = load(tmp_draft).meta
    assert m.status == Status.posted
    assert m.published_url == "https://x/1"
    assert m.published_at == NOW
    assert m.published_text == "second"


def test_mark_posted_with_explicit_multiline_text(tmp_draft: Path):
    _choose(tmp_draft)
    approve(tmp_draft)
    mark_posted(tmp_draft, "https://x/1", "edited\nby hand", NOW)
    assert load(tmp_draft).meta.published_text == "edited\nby hand"


def test_mark_posted_without_chosen_and_without_text_raises(tmp_draft: Path):
    d = load(tmp_draft)
    d.meta.status = Status.approved
    save(d)
    with pytest.raises(DraftError):
        mark_posted(tmp_draft, "https://x/1", None, NOW)
    assert load(tmp_draft).meta.status == Status.approved
    mark_posted(tmp_draft, "https://x/1", "manual", NOW)
    assert load(tmp_draft).meta.published_text == "manual"


def test_chosen_text_raises_without_choice(tmp_draft: Path):
    with pytest.raises(DraftError):
        chosen_text(load(tmp_draft))


def test_add_media_appends_paths(tmp_draft: Path, tmp_path: Path):
    f = tmp_path / "a.png"
    f.write_bytes(b"x")
    add_media(tmp_draft, [f])
    assert load(tmp_draft).meta.media == [str(f)]


def test_add_media_refuses_posted(tmp_draft: Path, tmp_path: Path):
    f = tmp_path / "a.png"
    f.write_bytes(b"x")
    _choose(tmp_draft)
    approve(tmp_draft)
    mark_posted(tmp_draft, "u", None, NOW)
    with pytest.raises(DraftError):
        add_media(tmp_draft, [f])


def test_add_media_refuses_scheduled(tmp_draft: Path, tmp_path: Path):
    f = tmp_path / "a.png"
    f.write_bytes(b"x")
    d = load(tmp_draft)
    d.meta.status = Status.scheduled
    save(d)
    with pytest.raises(DraftError):
        add_media(tmp_draft, [f])


def test_add_media_requires_existing_file(tmp_draft: Path, tmp_path: Path):
    with pytest.raises(DraftError):
        add_media(tmp_draft, [tmp_path / "missing.png"])
    assert load(tmp_draft).meta.media == []


def test_save_is_atomic_no_partial_file_on_error(tmp_draft: Path, monkeypatch: pytest.MonkeyPatch):
    original = tmp_draft.read_text()
    d = load(tmp_draft)
    d.variants[0] = "changed"

    def boom(*a: object, **k: object) -> None:
        raise OSError("disk gone")

    monkeypatch.setattr("promo.drafts.os.replace", boom)
    with pytest.raises(OSError):
        save(d)
    assert tmp_draft.read_text() == original
    assert os.listdir(tmp_draft.parent) == [tmp_draft.name]


def test_save_creates_missing_parent_directories(tmp_path: Path):
    p = tmp_path / "drafts" / "camp" / "beat" / "d.md"
    save(Draft(meta=_meta(), variants=["a", "b", "c"], path=p))
    assert load(p).variants == ["a", "b", "c"]


@pytest.mark.parametrize(
    "bad",
    [
        "intro\n## Variant 2\nmore",
        "text\n## Variant 2",
        "```\n## Variant 2\n```",
        "## Variant 7",
    ],
)
def test_render_refuses_heading_like_lines(bad: str):
    with pytest.raises(DraftError, match="heading"):
        render(_meta(), ["a", bad, "c"])


def test_render_refuses_count_mismatch():
    with pytest.raises(DraftError, match="variants"):
        render(_meta(variants=2), ["a", "b", "c"])


def test_save_refuses_unloadable_and_leaves_original(tmp_draft: Path):
    original = tmp_draft.read_bytes()
    d = load(tmp_draft)
    d.variants[1] = "x\n## Variant 2\ny"
    with pytest.raises(DraftError):
        save(d)
    assert tmp_draft.read_bytes() == original
    assert os.listdir(tmp_draft.parent) == [tmp_draft.name]


def test_save_refusal_creates_no_directories(tmp_path: Path):
    p = tmp_path / "new" / "dir" / "d.md"
    with pytest.raises(DraftError):
        save(Draft(meta=_meta(), variants=["a", "", "c"], path=p))
    assert not (tmp_path / "new").exists()


def _roundtrip(variants: list[str]) -> list[str]:
    meta = _meta(variants=len(variants))
    return parse(render(meta, variants), Path("x.md")).variants


def test_variant_indentation_and_trailing_spaces_survive():
    assert _roundtrip(["  indented\nsecond  ", "b"]) == ["  indented\nsecond  ", "b"]


def test_variant_crlf_and_cr_become_lf():
    assert _roundtrip(["  ind\r\nx\ry", "b"]) == ["  ind\nx\ny", "b"]


def test_variant_framing_blank_lines_are_stripped():
    assert _roundtrip(["\n\nbody\n\n", "b"]) == ["body", "b"]


def test_variant_with_triple_dash_line_roundtrips():
    v = ["before\n---\nafter", "b"]
    assert _roundtrip(v) == v


def test_variant_non_ascii_roundtrips():
    v = ["Καλημέρα \U0001f680 café", "日本語"]
    assert _roundtrip(v) == v


@pytest.mark.parametrize("empty", ["", "   ", "\n\n", " \n \t\n"])
def test_render_refuses_empty_variant(empty: str):
    with pytest.raises(DraftError, match="empty"):
        render(_meta(), ["a", empty, "c"])


def test_parse_rejects_hand_edited_empty_variant():
    text = render(_meta(), ["a", "b", "c"]).replace("\nb\n", "\n \n")
    with pytest.raises(DraftError, match="empty"):
        parse(text, Path("x.md"))


def test_load_wraps_non_utf8_file(tmp_path: Path):
    bad = tmp_path / "bad.md"
    bad.write_bytes(b"\xff\xfe bad")
    with pytest.raises(DraftError, match="cannot read draft"):
        load(bad)


def test_unapprove_and_mark_posted_refuse_posted_draft(tmp_draft: Path):
    _choose(tmp_draft)
    approve(tmp_draft)
    mark_posted(tmp_draft, "https://x/1", None, NOW)
    before = tmp_draft.read_bytes()
    with pytest.raises(DraftError):
        unapprove(tmp_draft)
    with pytest.raises(DraftError):
        mark_posted(tmp_draft, "https://x/2", "other", NOW)
    assert tmp_draft.read_bytes() == before
    assert load(tmp_draft).meta.published_url == "https://x/1"
