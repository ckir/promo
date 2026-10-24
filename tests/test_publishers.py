from typing import Protocol

import promo.publishers as publishers


def test_no_publisher_implementations_registered() -> None:
    assert publishers.__all__ == ["Publisher"]


def test_publisher_is_a_bare_protocol() -> None:
    assert Protocol in publishers.Publisher.__mro__
    assert getattr(publishers.Publisher, "_is_protocol", False) is True
    public = [name for name in dir(publishers) if not name.startswith("_")]
    assert public == ["Publisher"]


def test_publisher_declares_only_publish_and_fetch_metrics() -> None:
    members = {name for name in vars(publishers.Publisher) if not name.startswith("_")}
    assert members == {"publish", "fetch_metrics"}
