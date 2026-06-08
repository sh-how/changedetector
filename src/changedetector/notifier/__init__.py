"""Alert delivery abstraction.

A Notifier sends a text message with an optional image. Telegram is the first
concrete channel; the protocol keeps Discord/desktop additions trivial.
"""

from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable


class NotifierError(Exception):
    """Raised when an alert fails to deliver."""


@runtime_checkable
class Notifier(Protocol):
    def send(self, text: str, image_bytes: Optional[bytes] = None) -> None: ...


def build_notifier(channel: str, secrets) -> Notifier:
    """Construct the configured notifier from the alert channel + secrets."""
    if channel == "telegram":
        from .telegram import TelegramNotifier

        return TelegramNotifier(secrets.telegram_bot_token, secrets.telegram_chat_id)
    if channel == "console":
        from .console import ConsoleNotifier

        return ConsoleNotifier()
    raise NotifierError(f"unknown alert channel: {channel}")
