setup:
    uv sync

lint:
    uv run ruff check .
    uv run ruff format --check .

format:
    uv run ruff format .

typecheck:
    uv run mypy src

test:
    uv run pytest

check: lint typecheck test
