from typer.testing import CliRunner

from promo.cli import app


def test_version_flag_prints_version() -> None:
    result = CliRunner().invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "promo 0.1.0" in result.stdout
