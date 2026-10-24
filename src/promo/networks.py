# Copyright (c) 2026 Costas Kirgoussios
#
# This software is licensed under the PolyForm Noncommercial License 1.0.0.
# You may obtain a copy of the License at:
# https://polyformproject.org/licenses/noncommercial/1.0.0/

"""Per-network character limits, hashtag caps and measurement rules."""

import re

from promo.config import Settings
from promo.schema import Network

LIMITS: dict[Network, int] = {
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

NEEDS_MEDIA: frozenset[Network] = frozenset({Network.instagram, Network.tiktok, Network.pinterest})

HASHTAG_CAPS: dict[Network, int] = {
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

URL_FIXED_LENGTH: dict[Network, int] = {Network.x: 23, Network.mastodon: 23}

_URL = re.compile(r"https?://\S+")


def measured_length(text: str, network: Network) -> int:
    """Length of text as the network counts it (URLs fixed where the network does so)."""
    fixed = URL_FIXED_LENGTH.get(network)
    if fixed is None:
        return len(text)
    return len(_URL.sub("U" * fixed, text))


def limit_for(network: Network, settings: Settings) -> int:
    override = settings.networks.get(network.value)
    if override is not None and override.limit is not None:
        return override.limit
    return LIMITS[network]


def hashtag_cap_for(network: Network, settings: Settings) -> int:
    override = settings.networks.get(network.value)
    if override is not None and override.hashtag_cap is not None:
        return override.hashtag_cap
    return HASHTAG_CAPS[network]
