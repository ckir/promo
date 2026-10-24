# Copyright (c) 2026 Costas Kirgoussios
#
# This software is licensed under the PolyForm Noncommercial License 1.0.0.
# You may obtain a copy of the License at:
# https://polyformproject.org/licenses/noncommercial/1.0.0/

import re
from collections.abc import Callable
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from typing import Any

import pytest
from conftest import DraftsTree
from rich.console import Console
from typer.testing import CliRunner

from promo import drafts
from promo.cli import app
from promo.drafts import Status
from promo.generators.fake import FakeGenerator
from promo.review import (
    ReviewIOError,
    ReviewSummary,
    TerminalIO,
    review,
    sanitize,
    select_for_review,
)

NOW = datetime(2026, 10, 24, 12, 0, tzinfo=UTC)


class ScriptedIO:
    def __init__(
        self,
        keys: list[str],
        lines: list[str | None] | None = None,
        *,
        copy_ok: bool = True,
        edit: Callable[[Path], None] | None = None,
    ) -> None:
        self.keys = list(keys)
        self.lines: list[str | None] = list(lines or [])
        self.copy_ok = copy_ok
        self.edit_cb = edit
        self.printed: list[str] = []
        self.copies: list[str] = []
        self.edited: list[Path] = []

    def read_key(self) -> str:
        return self.keys.pop(0) if self.keys else "q"

    def read_line(self, prompt: str) -> str | None:
        return self.lines.pop(0) if self.lines else None

    def print(self, renderable: Any) -> None:
        buf = StringIO()
        Console(file=buf, width=100, color_system=None, highlight=False).print(renderable)
        self.printed.append(buf.getvalue())

    def copy(self, text: str) -> bool:
        self.copies.append(text)
        return self.copy_ok

    def edit(self, path: Path) -> None:
        self.edited.append(path)
        if self.edit_cb:
            self.edit_cb(path)

    @property
    def output(self) -> str:
        return "\n".join(self.printed)


def _run(
    tree: DraftsTree, io: ScriptedIO, *, all_: bool = False, generator: FakeGenerator | None = None
) -> ReviewSummary:
    c = tree.campaign
    gen = generator or FakeGenerator()
    return review(
        c.drafts_root,
        c.campaign,
        io,
        all_=all_,
        manifest=c.manifest,
        settings=c.settings,
        now=NOW,
        generator_factory=lambda profile, key: gen,
    )


def test_select_default_scope_and_all_scope(drafts_tree: DraftsTree) -> None:
    p = drafts_tree.paths
    root, camp = drafts_tree.root, drafts_tree.campaign.campaign
    default = select_for_review(root, camp, all_=False)
    assert default == sorted([p["draft"], p["draft_warn"], p["approved_warn"]])
    everything = select_for_review(root, camp, all_=True)
    assert everything == sorted(
        [p["draft"], p["draft_warn"], p["approved_warn"], p["approved_clean"]]
    )


def test_select_skips_unreadable_and_rejects_bad_campaign(drafts_tree: DraftsTree) -> None:
    from promo.schema import ManifestError

    drafts_tree.paths["draft"].write_text("garbage", encoding="utf-8")
    got = select_for_review(drafts_tree.root, drafts_tree.campaign.campaign, all_=False)
    assert drafts_tree.paths["draft"] not in got
    with pytest.raises(ManifestError):
        select_for_review(drafts_tree.root, "../x", all_=False)


def test_choose_then_approve(drafts_tree: DraftsTree) -> None:
    path = drafts_tree.paths["draft"]
    # sorted order: approved_warn(launch/x), draft_warn(teaser/linkedin), draft(teaser/x)
    summary = _run(drafts_tree, ScriptedIO(["s", "s", "2", "a", "q"]))
    d = drafts.load(path)
    assert d.meta.status is Status.approved
    assert d.meta.chosen == 2
    assert summary == ReviewSummary(approved=1, skipped=2, regenerated=0)


def test_approve_without_chosen_shows_error_and_stays(drafts_tree: DraftsTree) -> None:
    path = drafts_tree.paths["draft"]
    io = ScriptedIO(["s", "s", "a", "q"])
    summary = _run(drafts_tree, io)
    assert drafts.load(path).meta.status is Status.draft
    assert "without a chosen variant" in io.output
    assert summary.approved == 0


def test_copy_falls_back_to_print_when_clipboard_fails(drafts_tree: DraftsTree) -> None:
    io = ScriptedIO(["s", "s", "3", "c", "q"], copy_ok=False)
    _run(drafts_tree, io)
    assert io.copies == ["draft three"]
    assert "clipboard unavailable" in io.output
    assert io.printed[-2].strip() == "draft three" or "draft three" in io.printed[-2]


def test_copy_without_chosen_is_error(drafts_tree: DraftsTree) -> None:
    io = ScriptedIO(["s", "s", "c", "q"])
    _run(drafts_tree, io)
    assert io.copies == []
    assert "no variant has been chosen" in io.output


def test_out_of_range_digit_is_error(drafts_tree: DraftsTree) -> None:
    io = ScriptedIO(["s", "s", "9", "q"])
    _run(drafts_tree, io)
    assert "no variant 9" in io.output
    assert drafts.load(drafts_tree.paths["draft"]).meta.chosen is None


def test_edit_reloads_file_and_keeps_external_change(drafts_tree: DraftsTree) -> None:
    path = drafts_tree.paths["draft"]

    def rewrite(p: Path) -> None:
        d = drafts.load(p)
        d.variants[0] = "edited by hand"
        drafts.save(d)

    io = ScriptedIO(["s", "s", "e", "1", "a", "q"], edit=rewrite)
    _run(drafts_tree, io)
    d = drafts.load(path)
    assert io.edited == [path]
    assert d.meta.status is Status.approved
    assert drafts.chosen_text(d) == "edited by hand"


def test_edit_that_breaks_headings_is_reported_not_approved(drafts_tree: DraftsTree) -> None:
    path = drafts_tree.paths["draft"]

    def ruin(p: Path) -> None:
        p.write_text(p.read_text(encoding="utf-8").replace("## Variant 2", "## Oops"), "utf-8")

    io = ScriptedIO(["s", "s", "e", "a", "q"], edit=ruin)
    summary = _run(drafts_tree, io)
    assert "variant headings" in io.output
    assert summary.approved == 0
    assert "## Oops" in path.read_text(encoding="utf-8")


def test_broken_file_only_accepts_e_s_q(drafts_tree: DraftsTree) -> None:
    path = drafts_tree.paths["approved_warn"]  # first in sorted order
    good = path.read_text(encoding="utf-8")
    calls: list[int] = []

    def toggle(p: Path) -> None:
        calls.append(1)
        p.write_text("not a draft" if len(calls) == 1 else good, encoding="utf-8")

    io = ScriptedIO(["e", "a", "1", "c", "r", "e", "s", "q"], edit=toggle)
    summary = _run(drafts_tree, io)
    # a, 1, c, r are refused on the unreadable draft; the second edit restores it
    assert io.output.count("only e, s and q") == 4
    assert summary.skipped == 1
    assert summary.approved == 0
    assert path.read_text(encoding="utf-8") == good


def test_regenerate_resets_chosen_and_uses_recorded_profile(drafts_tree: DraftsTree) -> None:
    path = drafts_tree.paths["draft"]
    d = drafts.load(path)
    d.meta.chosen = 2
    drafts.save(d)
    gen = FakeGenerator(responses=[["fresh one", "fresh two", "fresh three"]])
    io = ScriptedIO(["s", "s", "r", "q"], ["make it punchier"])
    summary = _run(drafts_tree, io, generator=gen)
    after = drafts.load(path)
    assert summary.regenerated == 1
    assert after.meta.chosen is None
    assert after.meta.profile == "claude"
    assert after.variants == ["fresh one", "fresh two", "fresh three"]
    assert "make it punchier" in gen.requests[0].user


def test_regenerate_shows_error_and_continues_on_generation_error(
    drafts_tree: DraftsTree,
) -> None:
    path = drafts_tree.paths["draft"]
    original = path.read_text(encoding="utf-8")
    io = ScriptedIO(["s", "s", "r", "2", "q"], [""])
    summary = _run(drafts_tree, io, generator=FakeGenerator(fail_after=0))
    assert "fake generator failure" in io.output
    assert summary.regenerated == 0
    after = path.read_text(encoding="utf-8")
    assert after != original  # only because "2" chose a variant on the same draft
    assert drafts.load(path).meta.chosen == 2


def test_markup_and_escape_sequences_in_variants_are_neutralised(
    drafts_tree: DraftsTree,
) -> None:
    path = drafts_tree.paths["draft"]
    d = drafts.load(path)
    d.variants[0] = "[red]x[/red] and [bold]y"
    d.variants[1] = "evil \x1b[31mred\x1b[0m \x1b]0;title\x07 bell\x07 c1\x85 end"
    drafts.save(d)
    io = ScriptedIO(["s", "s", "q"])
    _run(drafts_tree, io)
    assert "[red]x[/red] and [bold]y" in io.output
    assert "\x1b" not in io.output
    assert "\x07" not in io.output
    assert "\x85" not in io.output
    assert "evil red" in io.output


def test_sanitize_keeps_newline_and_tab() -> None:
    assert sanitize("a\tb\nc\x00d\x7fe\x9bf") == "a\tb\ncdef"


def test_warning_details_and_media_hint(drafts_tree: DraftsTree) -> None:
    path = drafts_tree.paths["draft_warn"]
    d = drafts.load(path)
    d.variants[0] = "This is guaranteed to work in 99 ways"
    d.meta.warnings = ["prohibited_claim", "unsourced_number"]
    d.meta.needs_media = True
    drafts.save(d)
    io = ScriptedIO(["s", "q"])
    _run(drafts_tree, io)
    assert re.search(r"variant 1 matches: guaranteed", io.output)
    assert re.search(r"variant 1 unsourced: 99", io.output)
    assert "promo media" in io.output


def test_q_returns_immediately_and_leaves_files_untouched(drafts_tree: DraftsTree) -> None:
    snapshot = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in drafts_tree.paths.values()}
    summary = _run(drafts_tree, ScriptedIO(["q"]))
    assert summary == ReviewSummary(0, 0, 0)
    for p, (data, mtime) in snapshot.items():
        assert (p.read_bytes(), p.stat().st_mtime_ns) == (data, mtime)


def test_review_cli_refuses_non_tty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, drafts_tree: DraftsTree
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("promo.cli.sys.stdin.isatty", lambda: False)
    before = {p: p.stat().st_mtime_ns for p in drafts_tree.paths.values()}
    result = CliRunner().invoke(app, ["review", drafts_tree.campaign.campaign])
    assert result.exit_code == 1
    assert "promo review needs an interactive terminal" in result.output
    assert {p: p.stat().st_mtime_ns for p in drafts_tree.paths.values()} == before


def test_edit_failure_shows_error_and_continues(drafts_tree: DraftsTree) -> None:
    def boom(p: Path) -> None:
        raise ReviewIOError("cannot run editor 'nope'")

    io = ScriptedIO(["e", "s", "s", "s", "q"], edit=boom)
    summary = _run(drafts_tree, io)
    assert "cannot run editor 'nope'" in io.output
    assert summary.skipped == 3


def test_terminal_edit_nonexistent_editor(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("EDITOR", "/nonexistent/ed")
    with pytest.raises(ReviewIOError, match="cannot run editor"):
        TerminalIO().edit(tmp_path / "x.md")


def test_terminal_edit_empty_editor_falls_back_to_vi(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[list[str]] = []
    monkeypatch.setenv("EDITOR", "")
    monkeypatch.setattr("promo.review.subprocess.run", lambda argv, check: calls.append(argv))
    TerminalIO().edit(tmp_path / "x.md")
    assert calls == [["vi", str(tmp_path / "x.md")]]


def test_terminal_edit_unbalanced_quote(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("EDITOR", "vi 'x")
    with pytest.raises(ReviewIOError, match="cannot run editor"):
        TerminalIO().edit(tmp_path / "x.md")


@pytest.mark.parametrize("key", ["²", "٣", "0"])
def test_non_ascii_digit_keys_are_unknown_not_fatal(drafts_tree: DraftsTree, key: str) -> None:
    io = ScriptedIO([key, "s", "s", "s"])
    summary = _run(drafts_tree, io)
    assert "unknown key" in io.output
    assert summary.skipped == 3


@pytest.mark.parametrize(
    "code",
    [
        0x200B, 0x200E, 0x200F, 0x202A, 0x202B, 0x202C, 0x202D, 0x202E, 0x2060,
        0x2066, 0x2067, 0x2068, 0x2069, 0x2028, 0x2029, 0xFEFF, 0x061C,
    ],
)  # fmt: skip
def test_sanitize_strips_bidi_and_invisible(code: int) -> None:
    assert sanitize(f"a{chr(code)}b") == "ab"


@pytest.mark.parametrize("code", [0x200C, 0x200D])
def test_sanitize_keeps_joiners(code: int) -> None:
    assert sanitize(f"a{chr(code)}b") == f"a{chr(code)}b"


def test_sanitize_keeps_zwj_emoji_sequence() -> None:
    family = "\U0001f468\u200d\U0001f469\u200d\U0001f467"
    assert sanitize(family) == family


def test_terminal_io_keyboard_interrupt_acts_like_eof(monkeypatch: pytest.MonkeyPatch) -> None:
    def interrupt(prompt: str = "") -> str:
        raise KeyboardInterrupt

    monkeypatch.setattr("builtins.input", interrupt)
    assert TerminalIO().read_key() == "q"
    assert TerminalIO().read_line("note: ") is None


def test_terminal_io_eof_cancels_note(monkeypatch: pytest.MonkeyPatch) -> None:
    def eof(prompt: str = "") -> str:
        raise EOFError

    monkeypatch.setattr("builtins.input", eof)
    assert TerminalIO().read_line("note: ") is None
    assert TerminalIO().read_key() == "q"


def test_cancelled_note_does_not_regenerate(drafts_tree: DraftsTree) -> None:
    path = drafts_tree.paths["draft"]
    before = (path.read_bytes(), path.stat().st_mtime_ns)
    gen = FakeGenerator()
    called: list[int] = []

    def factory(profile: object, key: object) -> FakeGenerator:
        called.append(1)
        return gen

    c = drafts_tree.campaign
    io = ScriptedIO(["s", "s", "r", "q"], [None])
    summary = review(
        c.drafts_root,
        c.campaign,
        io,
        all_=False,
        manifest=c.manifest,
        settings=c.settings,
        now=NOW,
        generator_factory=factory,  # type: ignore[arg-type]
    )
    assert "cancelled" in io.output
    assert called == [] and gen.requests == []
    assert summary.regenerated == 0
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before


def test_empty_note_line_still_regenerates(drafts_tree: DraftsTree) -> None:
    gen = FakeGenerator(responses=[["n1", "n2", "n3"]])
    io = ScriptedIO(["s", "s", "r", "q"], [""])
    summary = _run(drafts_tree, io, generator=gen)
    assert summary.regenerated == 1
    assert len(gen.requests) == 1


def test_terminal_edit_whitespace_editor_falls_back_to_vi(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[list[str]] = []
    monkeypatch.setenv("EDITOR", "   ")
    monkeypatch.setattr("promo.review.subprocess.run", lambda argv, check: calls.append(argv))
    TerminalIO().edit(tmp_path / "x.md")
    assert calls == [["vi", str(tmp_path / "x.md")]]


def test_terminal_edit_nonzero_exit_is_ignored(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("EDITOR", "false")
    TerminalIO().edit(tmp_path / "x.md")


def test_terminal_edit_keyboard_interrupt_is_review_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def interrupt(argv: list[str], check: bool) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr("promo.review.subprocess.run", interrupt)
    with pytest.raises(ReviewIOError, match="editor interrupted"):
        TerminalIO().edit(tmp_path / "x.md")


def test_non_draft_status_refuses_choose_and_regenerate(drafts_tree: DraftsTree) -> None:
    path = drafts_tree.paths["approved_clean"]
    before = path.read_text(encoding="utf-8")
    did = drafts.load(path).meta.id
    gen = FakeGenerator()
    io = ScriptedIO(["3", "r", "a", "q"], ["note"])
    _run(drafts_tree, io, all_=True, generator=gen)
    after = drafts.load(path)
    assert after.meta.chosen == 1
    assert after.meta.status is Status.approved
    assert path.read_text(encoding="utf-8") == before
    assert gen.requests == []
    assert io.output.count(f"run `promo unapprove {did}` first") >= 2
    assert "already approved" in io.output
    assert "cannot approve a draft with status approved" not in io.output
