# Copyright (c) 2026 Costas Kirgoussios
#
# This software is licensed under the PolyForm Noncommercial License 1.0.0.
# You may obtain a copy of the License at:
# https://polyformproject.org/licenses/noncommercial/1.0.0/

import pytest

from promo.config import NetworkOverride, Settings
from promo.networks import (
    HASHTAG_CAPS,
    LIMITS,
    NEEDS_MEDIA,
    URL_FIXED_LENGTH,
    hashtag_cap_for,
    limit_for,
    measured_length,
)
from promo.schema import Network

EXPECTED_LIMITS = {
    Network.x: 280,
    Network.threads: 500,
    Network.bluesky: 300,
    Network.mastodon: 500,
    Network.linkedin: 3000,
    Network.instagram: 2200,
    Network.facebook: 5000,
    Network.tiktok: 2200,
    Network.pinterest: 500,
}

EXPECTED_CAPS = {
    Network.instagram: 30,
    Network.x: 3,
    Network.linkedin: 5,
    Network.threads: 5,
    Network.mastodon: 5,
    Network.bluesky: 3,
    Network.facebook: 5,
    Network.tiktok: 5,
    Network.pinterest: 5,
}


def _settings(**networks: NetworkOverride) -> Settings:
    return Settings.model_construct(networks=dict(networks), default_profile="claude", profiles={})


@pytest.mark.parametrize("network", list(Network))
def test_limits_pinned(network: Network) -> None:
    assert LIMITS[network] == EXPECTED_LIMITS[network]


@pytest.mark.parametrize("network", list(Network))
def test_hashtag_caps_pinned(network: Network) -> None:
    assert HASHTAG_CAPS[network] == EXPECTED_CAPS[network]


def test_tables_cover_every_network() -> None:
    assert set(LIMITS) == set(HASHTAG_CAPS) == set(Network)


def test_needs_media() -> None:
    assert NEEDS_MEDIA == frozenset({Network.instagram, Network.tiktok, Network.pinterest})


def test_url_fixed_length() -> None:
    assert URL_FIXED_LENGTH == {Network.x: 23, Network.mastodon: 23}


def test_measured_length_url_fixed_on_x() -> None:
    assert measured_length("see https://example.com/a-very-long-path", Network.x) == 4 + 23


def test_measured_length_url_fixed_on_mastodon() -> None:
    assert measured_length("a http://e.co/x b", Network.mastodon) == 2 + 23 + 2


def test_measured_length_literal_on_linkedin() -> None:
    text = "see https://example.com/a-very-long-path"
    assert measured_length(text, Network.linkedin) == len(text)


def test_limit_override() -> None:
    s = _settings(x=NetworkOverride(limit=200, hashtag_cap=1))
    assert limit_for(Network.x, s) == 200
    assert hashtag_cap_for(Network.x, s) == 1


def test_override_absent_or_none_falls_back() -> None:
    s = _settings(x=NetworkOverride(limit=None, hashtag_cap=None))
    assert limit_for(Network.x, s) == 280
    assert hashtag_cap_for(Network.x, s) == 3
    assert limit_for(Network.bluesky, s) == 300
    assert hashtag_cap_for(Network.bluesky, s) == 3


def test_partial_override() -> None:
    s = _settings(threads=NetworkOverride(limit=400))
    assert limit_for(Network.threads, s) == 400
    assert hashtag_cap_for(Network.threads, s) == 5
