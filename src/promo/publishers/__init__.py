# Copyright (c) 2026 Costas Kirgoussios
#
# This software is licensed under the PolyForm Noncommercial License 1.0.0.
# You may obtain a copy of the License at:
# https://polyformproject.org/licenses/noncommercial/1.0.0/

"""Publisher interface placeholder.

No publisher implementation exists in milestone 1. The milestone-1 CLI cannot
publish anything and holds no social-network credentials; ``promo posted`` only
records a URL that the owner entered by hand. This module fixes the shape a
later milestone will implement, with no registry and no adapters.
"""

import typing as _typing

if _typing.TYPE_CHECKING:
    from promo.drafts import Draft

__all__ = ["Publisher"]


class Publisher(_typing.Protocol):
    """A social network that can publish an approved draft and report metrics."""

    def publish(self, draft: "Draft") -> tuple[str, str]:
        """Publish the draft and return ``(remote_id, url)``."""
        ...

    def fetch_metrics(self, remote_id: str) -> dict[str, float | None]:
        """Return metrics by name; ``None`` means unavailable, never zero."""
        ...
