"""A no-network notifier that logs alerts. Used for dry-runs and tests."""

from __future__ import annotations

import logging
from typing import Optional

log = logging.getLogger("changedetector.notifier.console")


class ConsoleNotifier:
    def send(self, text: str, image_bytes: Optional[bytes] = None) -> None:
        suffix = f" (+{len(image_bytes)} bytes image)" if image_bytes else ""
        log.info("ALERT: %s%s", text, suffix)
